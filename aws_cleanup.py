#!/usr/bin/env python3
"""
AWS Account Cleanup - Remove todos os serviços AWS
ATENÇÃO: Este script REMOVERÁ PERMANENTEMENTE todos os recursos da conta AWS
Use apenas em contas de sandbox/teste/desenvolvimento
"""

import boto3
import botocore
from botocore.exceptions import ClientError, BotoCoreError
import concurrent.futures
import json
import time
from datetime import datetime
import argparse
import sys
from typing import Dict, List, Optional

class AWSCleanup:
    def __init__(self, region='us-east-1', max_workers=10, dry_run=False):
        """Inicializa o cliente de limpeza AWS"""
        self.region = region
        self.dry_run = dry_run
        self.max_workers = max_workers
        self.session = boto3.Session(region_name=region)
        self.clients = {}
        self.deleted_resources = []
        self.failed_resources = []
        
        # Configurar logging
        self.log_file = f"aws_cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    def get_client(self, service_name):
        """Obtém cliente boto3 para um serviço"""
        if service_name not in self.clients:
            self.clients[service_name] = self.session.client(service_name)
        return self.clients[service_name]
    
    def log_action(self, service, resource_type, resource_id, action, success=True, error=None):
        """Registra ações realizadas"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'service': service,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'action': action,
            'success': success,
            'dry_run': self.dry_run,
            'error': str(error) if error else None
        }
        
        if success:
            self.deleted_resources.append(log_entry)
        else:
            self.failed_resources.append(log_entry)
        
        # Imprime no console
        prefix = "[DRY RUN] " if self.dry_run else ""
        status = "✓" if success else "✗"
        print(f"{prefix}{status} {service}.{resource_type}: {resource_id} - {action}")
        
        # Salva em arquivo
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def wait_for_deletion(self, service, resource_id, check_func, timeout=300):
        """Aguarda até que o recurso seja deletado"""
        if self.dry_run:
            return True
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if not check_func():
                    return True
            except Exception:
                return True
            time.sleep(5)
        return False
    
    def empty_s3_bucket(self, bucket_name):
        """Esvazia bucket S3 completamente"""
        s3 = self.get_client('s3')
        s3_resource = self.session.resource('s3')
        
        try:
            bucket = s3_resource.Bucket(bucket_name)
            
            # Deletar todas as versões de objetos
            bucket.object_versions.all().delete()
            
            # Deletar objetos deletados (versionamento)
            bucket.objects.all().delete()
            
            # Deletar objetos com delete markers
            for obj in bucket.objects.all():
                obj.delete()
            
            return True
        except Exception as e:
            self.log_action('s3', 'bucket', bucket_name, 'empty_bucket', False, e)
            return False
    
    def cleanup_s3(self):
        """Remove todos os buckets S3"""
        s3 = self.get_client('s3')
        
        try:
            buckets = s3.list_buckets()
            
            for bucket in buckets['Buckets']:
                bucket_name = bucket['Name']
                
                try:
                    # Pular buckets com políticas que impedem deleção
                    try:
                        policy = s3.get_bucket_policy(Bucket=bucket_name)
                        if 'Deny' in str(policy).lower():
                            self.log_action('s3', 'bucket', bucket_name, 'skip_protected', True)
                            continue
                    except:
                        pass
                    
                    # Esvaziar bucket
                    if not self.dry_run:
                        if not self.empty_s3_bucket(bucket_name):
                            continue
                    
                    # Deletar bucket
                    if self.dry_run:
                        action = 'would_delete'
                    else:
                        s3.delete_bucket(Bucket=bucket_name)
                        action = 'deleted'
                    
                    self.log_action('s3', 'bucket', bucket_name, action, True)
                    
                except Exception as e:
                    self.log_action('s3', 'bucket', bucket_name, 'delete', False, e)
                    
        except Exception as e:
            print(f"Erro ao limpar S3: {e}")
    
    def cleanup_ec2(self):
        """Remove todos os recursos EC2"""
        ec2 = self.get_client('ec2')
        ec2_resource = self.session.resource('ec2')
        
        # 1. Terminar instâncias EC2
        instances = ec2.describe_instances()
        instance_ids = []
        
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                if instance['State']['Name'] not in ['terminated', 'shutting-down']:
                    instance_ids.append(instance['InstanceId'])
        
        if instance_ids:
            if self.dry_run:
                for instance_id in instance_ids:
                    self.log_action('ec2', 'instance', instance_id, 'would_terminate', True)
            else:
                ec2.terminate_instances(InstanceIds=instance_ids)
                for instance_id in instance_ids:
                    self.log_action('ec2', 'instance', instance_id, 'terminated', True)
                
                # Aguardar término
                waiter = ec2.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=instance_ids)
        
        # 2. Remover security groups (exceto default)
        try:
            sgs = ec2.describe_security_groups()
            for sg in sgs['SecurityGroups']:
                if sg['GroupName'] != 'default':
                    if self.dry_run:
                        self.log_action('ec2', 'security_group', sg['GroupId'], 'would_delete', True)
                    else:
                        ec2.delete_security_group(GroupId=sg['GroupId'])
                        self.log_action('ec2', 'security_group', sg['GroupId'], 'deleted', True)
        except Exception as e:
            print(f"Erro ao limpar security groups: {e}")
        
        # 3. Remover volumes EBS disponíveis
        try:
            volumes = ec2.describe_volumes(Filters=[{'Name': 'status', 'Values': ['available']}])
            for volume in volumes['Volumes']:
                if self.dry_run:
                    self.log_action('ec2', 'volume', volume['VolumeId'], 'would_delete', True)
                else:
                    ec2.delete_volume(VolumeId=volume['VolumeId'])
                    self.log_action('ec2', 'volume', volume['VolumeId'], 'deleted', True)
        except Exception as e:
            print(f"Erro ao limpar volumes EBS: {e}")
        
        # 4. Remover snapshots (exceto públicos)
        try:
            snapshots = ec2.describe_snapshots(OwnerIds=['self'])
            for snapshot in snapshots['Snapshots']:
                if self.dry_run:
                    self.log_action('ec2', 'snapshot', snapshot['SnapshotId'], 'would_delete', True)
                else:
                    ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    self.log_action('ec2', 'snapshot', snapshot['SnapshotId'], 'deleted', True)
        except Exception as e:
            print(f"Erro ao limpar snapshots: {e}")
        
        # 5. Remover key pairs
        try:
            keys = ec2.describe_key_pairs()
            for key in keys['KeyPairs']:
                if self.dry_run:
                    self.log_action('ec2', 'key_pair', key['KeyName'], 'would_delete', True)
                else:
                    ec2.delete_key_pair(KeyName=key['KeyName'])
                    self.log_action('ec2', 'key_pair', key['KeyName'], 'deleted', True)
        except Exception as e:
            print(f"Erro ao limpar key pairs: {e}")
    
    def cleanup_vpc(self):
        """Remove todas as VPCs"""
        ec2 = self.get_client('ec2')
        ec2_resource = self.session.resource('ec2')
        
        try:
            vpcs = ec2.describe_vpcs()
            
            for vpc in vpcs['Vpcs']:
                vpc_id = vpc['VpcId']
                
                # Pular VPC padrão
                if vpc.get('IsDefault', False):
                    self.log_action('ec2', 'vpc', vpc_id, 'skip_default', True)
                    continue
                
                if self.dry_run:
                    self.log_action('ec2', 'vpc', vpc_id, 'would_delete', True)
                    continue
                
                try:
                    vpc_resource = ec2_resource.Vpc(vpc_id)
                    
                    # Remover endpoints
                    for ep in vpc_resource.vpc_endpoints.all():
                        ep.delete()
                    
                    # Remover NAT Gateways
                    for ng in vpc_resource.nat_gateways.all():
                        ng.delete()
                    
                    # Remover Egress Only Internet Gateways
                    for eigw in vpc_resource.egress_only_internet_gateways.all():
                        eigw.delete()
                    
                    # Remover Internet Gateways
                    for igw in vpc_resource.internet_gateways.all():
                        igw.detach_from_vpc(VpcId=vpc_id)
                        igw.delete()
                    
                    # Remover subnets
                    for subnet in vpc_resource.subnets.all():
                        subnet.delete()
                    
                    # Remover route tables (exceto main)
                    for rt in vpc_resource.route_tables.all():
                        if not rt.associations:
                            rt.delete()
                    
                    # Remover network ACLs (exceto default)
                    for acl in vpc_resource.network_acls.all():
                        if not acl.is_default:
                            acl.delete()
                    
                    # Remover VPC
                    ec2.delete_vpc(VpcId=vpc_id)
                    self.log_action('ec2', 'vpc', vpc_id, 'deleted', True)
                    
                except Exception as e:
                    self.log_action('ec2', 'vpc', vpc_id, 'delete', False, e)
                    
        except Exception as e:
            print(f"Erro ao limpar VPCs: {e}")
    
    def cleanup_rds(self):
        """Remove todas as instâncias RDS"""
        rds = self.get_client('rds')
        
        try:
            # Instâncias RDS
            instances = rds.describe_db_instances()
            for instance in instances['DBInstances']:
                instance_id = instance['DBInstanceIdentifier']
                
                if self.dry_run:
                    self.log_action('rds', 'instance', instance_id, 'would_delete', True)
                else:
                    try:
                        rds.delete_db_instance(
                            DBInstanceIdentifier=instance_id,
                            SkipFinalSnapshot=True,
                            DeleteAutomatedBackups=True
                        )
                        self.log_action('rds', 'instance', instance_id, 'deleted', True)
                    except Exception as e:
                        self.log_action('rds', 'instance', instance_id, 'delete', False, e)
            
            # Clusters RDS Aurora
            try:
                clusters = rds.describe_db_clusters()
                for cluster in clusters['DBClusters']:
                    cluster_id = cluster['DBClusterIdentifier']
                    
                    if self.dry_run:
                        self.log_action('rds', 'cluster', cluster_id, 'would_delete', True)
                    else:
                        try:
                            rds.delete_db_cluster(
                                DBClusterIdentifier=cluster_id,
                                SkipFinalSnapshot=True
                            )
                            self.log_action('rds', 'cluster', cluster_id, 'deleted', True)
                        except Exception as e:
                            self.log_action('rds', 'cluster', cluster_id, 'delete', False, e)
            except:
                pass
                
        except Exception as e:
            print(f"Erro ao limpar RDS: {e}")
    
    def cleanup_lambda(self):
        """Remove todas as funções Lambda"""
        lambda_client = self.get_client('lambda')
        
        try:
            functions = lambda_client.list_functions()
            
            for function in functions['Functions']:
                function_name = function['FunctionName']
                
                if self.dry_run:
                    self.log_action('lambda', 'function', function_name, 'would_delete', True)
                else:
                    try:
                        lambda_client.delete_function(FunctionName=function_name)
                        self.log_action('lambda', 'function', function_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('lambda', 'function', function_name, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar Lambda: {e}")
    
    def cleanup_cloudformation(self):
        """Remove todas as stacks CloudFormation"""
        cf = self.get_client('cloudformation')
        
        try:
            stacks = cf.describe_stacks()
            
            for stack in stacks['Stacks']:
                stack_name = stack['StackName']
                
                if self.dry_run:
                    self.log_action('cloudformation', 'stack', stack_name, 'would_delete', True)
                else:
                    try:
                        cf.delete_stack(StackName=stack_name)
                        self.log_action('cloudformation', 'stack', stack_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('cloudformation', 'stack', stack_name, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar CloudFormation: {e}")
    
    def cleanup_ecs(self):
        """Remove todos os serviços ECS"""
        ecs = self.get_client('ecs')
        
        try:
            # Listar todos os clusters
            clusters = ecs.list_clusters()
            
            for cluster_arn in clusters.get('clusterArns', []):
                cluster_name = cluster_arn.split('/')[-1]
                
                # Listar serviços no cluster
                services = ecs.list_services(cluster=cluster_arn)
                
                for service_arn in services.get('serviceArns', []):
                    service_name = service_arn.split('/')[-1]
                    
                    if self.dry_run:
                        self.log_action('ecs', 'service', f"{cluster_name}/{service_name}", 'would_delete', True)
                    else:
                        try:
                            # Atualizar serviço para 0 tasks
                            ecs.update_service(
                                cluster=cluster_arn,
                                service=service_name,
                                desiredCount=0
                            )
                            
                            # Deletar serviço
                            ecs.delete_service(
                                cluster=cluster_arn,
                                service=service_name
                            )
                            self.log_action('ecs', 'service', f"{cluster_name}/{service_name}", 'deleted', True)
                        except Exception as e:
                            self.log_action('ecs', 'service', f"{cluster_name}/{service_name}", 'delete', False, e)
                
                # Deletar cluster
                if not self.dry_run:
                    try:
                        ecs.delete_cluster(clusterArn=cluster_arn)
                        self.log_action('ecs', 'cluster', cluster_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('ecs', 'cluster', cluster_name, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar ECS: {e}")
    
    def cleanup_eks(self):
        """Remove todos os clusters EKS"""
        eks = self.get_client('eks')
        
        try:
            clusters = eks.list_clusters()
            
            for cluster_name in clusters.get('clusters', []):
                if self.dry_run:
                    self.log_action('eks', 'cluster', cluster_name, 'would_delete', True)
                else:
                    try:
                        eks.delete_cluster(name=cluster_name)
                        self.log_action('eks', 'cluster', cluster_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('eks', 'cluster', cluster_name, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar EKS: {e}")
    
    def cleanup_elasticache(self):
        """Remove todos os clusters Elasticache"""
        elasticache = self.get_client('elasticache')
        
        try:
            # Clusters Redis
            clusters = elasticache.describe_cache_clusters()
            for cluster in clusters.get('CacheClusters', []):
                cluster_id = cluster['CacheClusterId']
                
                if self.dry_run:
                    self.log_action('elasticache', 'cluster', cluster_id, 'would_delete', True)
                else:
                    try:
                        elasticache.delete_cache_cluster(CacheClusterId=cluster_id)
                        self.log_action('elasticache', 'cluster', cluster_id, 'deleted', True)
                    except Exception as e:
                        self.log_action('elasticache', 'cluster', cluster_id, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar Elasticache: {e}")
    
    def cleanup_load_balancers(self):
        """Remove todos os load balancers"""
        elbv2 = self.get_client('elbv2')
        
        try:
            # ALB/NLB
            load_balancers = elbv2.describe_load_balancers()
            
            for lb in load_balancers.get('LoadBalancers', []):
                lb_arn = lb['LoadBalancerArn']
                lb_name = lb['LoadBalancerName']
                
                if self.dry_run:
                    self.log_action('elbv2', 'load_balancer', lb_name, 'would_delete', True)
                else:
                    try:
                        elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
                        self.log_action('elbv2', 'load_balancer', lb_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('elbv2', 'load_balancer', lb_name, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar load balancers: {e}")
    
    def cleanup_api_gateway(self):
        """Remove todas as APIs do API Gateway"""
        apigw = self.get_client('apigateway')
        
        try:
            # API Gateway v1 (REST)
            apis = apigw.get_rest_apis()
            for api in apis.get('items', []):
                api_id = api['id']
                api_name = api['name']
                
                if self.dry_run:
                    self.log_action('apigateway', 'api', api_name, 'would_delete', True)
                else:
                    try:
                        apigw.delete_rest_api(restApiId=api_id)
                        self.log_action('apigateway', 'api', api_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('apigateway', 'api', api_name, 'delete', False, e)
            
            # API Gateway v2 (HTTP)
            try:
                apis_v2 = apigw.get_apis()
                for api in apis_v2.get('items', []):
                    api_id = api['apiId']
                    api_name = api.get('name', api_id)
                    
                    if self.dry_run:
                        self.log_action('apigatewayv2', 'api', api_name, 'would_delete', True)
                    else:
                        try:
                            apigw.delete_api(ApiId=api_id)
                            self.log_action('apigatewayv2', 'api', api_name, 'deleted', True)
                        except Exception as e:
                            self.log_action('apigatewayv2', 'api', api_name, 'delete', False, e)
            except:
                pass
                
        except Exception as e:
            print(f"Erro ao limpar API Gateway: {e}")
    
    def cleanup_dynamodb(self):
        """Remove todas as tabelas DynamoDB"""
        dynamodb = self.get_client('dynamodb')
        
        try:
            tables = dynamodb.list_tables()
            
            for table_name in tables.get('TableNames', []):
                if self.dry_run:
                    self.log_action('dynamodb', 'table', table_name, 'would_delete', True)
                else:
                    try:
                        dynamodb.delete_table(TableName=table_name)
                        self.log_action('dynamodb', 'table', table_name, 'deleted', True)
                    except Exception as e:
                        self.log_action('dynamodb', 'table', table_name, 'delete', False, e)
                        
        except Exception as e:
            print(f"Erro ao limpar DynamoDB: {e}")
    
    def scan_resources(self):
        """Varre todos os serviços para verificar recursos existentes"""
        print("\n" + "="*60)
        print("SCAN DE RECURSOS AWS")
        print("="*60)
        
        services_to_check = [
            ('EC2 Instâncias', self.get_client('ec2').describe_instances),
            ('S3 Buckets', self.get_client('s3').list_buckets),
            ('RDS Instâncias', self.get_client('rds').describe_db_instances),
            ('Lambda Functions', self.get_client('lambda').list_functions),
            ('CloudFormation Stacks', self.get_client('cloudformation').describe_stacks),
            ('VPCs', self.get_client('ec2').describe_vpcs),
            ('DynamoDB Tables', self.get_client('dynamodb').list_tables),
            ('EKS Clusters', self.get_client('eks').list_clusters),
            ('ECS Clusters', self.get_client('ecs').list_clusters),
        ]
        
        resource_count = {}
        
        for service_name, check_func in services_to_check:
            try:
                result = check_func()
                if service_name == 'EC2 Instâncias':
                    count = sum(len(res['Instances']) for res in result['Reservations'])
                elif service_name == 'S3 Buckets':
                    count = len(result['Buckets'])
                elif service_name == 'RDS Instâncias':
                    count = len(result['DBInstances'])
                elif service_name == 'Lambda Functions':
                    count = len(result['Functions'])
                elif service_name == 'CloudFormation Stacks':
                    count = len(result['Stacks'])
                elif service_name == 'VPCs':
                    count = len(result['Vpcs'])
                elif service_name == 'DynamoDB Tables':
                    count = len(result['TableNames'])
                elif service_name == 'EKS Clusters':
                    count = len(result.get('clusters', []))
                elif service_name == 'ECS Clusters':
                    count = len(result.get('clusterArns', []))
                else:
                    count = 0
                
                resource_count[service_name] = count
                print(f"{service_name:30} : {count}")
                
            except Exception as e:
                print(f"{service_name:30} : ERRO - {str(e)[:50]}")
                resource_count[service_name] = 'ERRO'
        
        return resource_count
    
    def cleanup_all(self):
        """Executa limpeza completa de todos os serviços"""
        print("\n" + "="*60)
        print("INICIANDO LIMPEZA COMPLETA DA CONTA AWS")
        print("="*60)
        
        if self.dry_run:
            print("MODO DRY RUN - Nenhum recurso será realmente deletado")
        
        start_time = time.time()
        
        # Ordem de deleção (importante para dependências)
        cleanup_methods = [
            ('ECS', self.cleanup_ecs),
            ('EKS', self.cleanup_eks),
            ('Lambda', self.cleanup_lambda),
            ('Elasticache', self.cleanup_elasticache),
            ('RDS', self.cleanup_rds),
            ('Load Balancers', self.cleanup_load_balancers),
            ('API Gateway', self.cleanup_api_gateway),
            ('EC2', self.cleanup_ec2),
            ('CloudFormation', self.cleanup_cloudformation),
            ('DynamoDB', self.cleanup_dynamodb),
            ('S3', self.cleanup_s3),
            ('VPC', self.cleanup_vpc),
        ]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for service_name, method in cleanup_methods:
                future = executor.submit(self.execute_cleanup, service_name, method)
                futures.append(future)
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Erro em thread: {e}")
        
        elapsed_time = time.time() - start_time
        
        print("\n" + "="*60)
        print("RESUMO DA LIMPEZA")
        print("="*60)
        print(f"Tempo total: {elapsed_time:.2f} segundos")
        print(f"Recursos deletados/simulados: {len(self.deleted_resources)}")
        print(f"Falhas: {len(self.failed_resources)}")
        print(f"Log salvo em: {self.log_file}")
        
        if self.failed_resources:
            print("\nRecursos com falha:")
            for failure in self.failed_resources:
                print(f"  - {failure['service']}.{failure['resource_type']}: {failure['resource_id']}")
    
    def execute_cleanup(self, service_name, method):
        """Executa método de limpeza com tratamento de erro"""
        try:
            print(f"\n[{service_name}] Iniciando limpeza...")
            method()
            print(f"[{service_name}] Limpeza concluída")
        except Exception as e:
            print(f"[{service_name}] ERRO: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Limpeza completa de conta AWS - REMOVE TODOS OS RECURSOS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXEMPLOS:
  %(prog)s --scan                      # Apenas escaneia recursos
  %(prog)s --dry-run                   # Simula deleção sem remover
  %(prog)s --region us-east-1          # Especifica região
  %(prog)s --confirm                   # Executa limpeza real
  %(prog)s --services ec2,s3,lambda    # Limpa serviços específicos

ATENÇÃO: Este script REMOVERÁ PERMANENTEMENTE recursos AWS.
         Use apenas em contas de sandbox/teste.
        """
    )
    
    parser.add_argument('--scan', action='store_true', 
                       help='Apenas escaneia recursos sem deletar')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Simula deleção sem remover recursos')
    parser.add_argument('--region', default='us-east-1', 
                       help='Região AWS (padrão: us-east-1)')
    parser.add_argument('--confirm', action='store_true',
                       help='Confirma execução real (requerido para deleção)')
    parser.add_argument('--services', 
                       help='Serviços específicos para limpar (separados por vírgula)')
    parser.add_argument('--max-workers', type=int, default=5,
                       help='Número máximo de threads paralelas')
    
    args = parser.parse_args()
    
    # Validação
    if not args.scan and not args.dry_run and not args.confirm:
        print("\nERRO: Você deve especificar --scan, --dry-run ou --confirm")
        print("Para deletar recursos reais, use: --confirm")
        sys.exit(1)
    
    if args.confirm and not args.dry_run:
        confirm = input(f"\n{'!'*60}\nATENÇÃO: Isso removerá PERMANENTEMENTE todos os recursos AWS na região {args.region}\n"
                       f"Deseja continuar? (digite 'SIM, DELETAR TUDO' para confirmar): ")
        if confirm != 'SIM, DELETAR TUDO':
            print("Operação cancelada.")
            sys.exit(0)
    
    # Executar
    cleanup = AWSCleanup(
        region=args.region,
        max_workers=args.max_workers,
        dry_run=args.dry_run or not args.confirm
    )
    
    # Scan inicial
    print(f"\nRegião: {args.region}")
    resource_count = cleanup.scan_resources()
    
    if args.scan:
        print("\nScan concluído. Use --dry-run para simular deleção.")
        sys.exit(0)
    
    if args.dry_run:
        print("\nIniciando simulação de deleção (dry-run)...")
        cleanup.cleanup_all()
    elif args.confirm:
        print(f"\n{'!'*60}")
        print("INICIANDO DELEÇÃO REAL DE RECURSOS!")
        print("Isso removerá permanentemente todos os recursos.")
        print(f"{'!'*60}")
        
        # Última confirmação
        final_confirm = input("\nDigite 'CONFIRMAR DELEÇÃO PERMANENTE' para continuar: ")
        if final_confirm == 'CONFIRMAR DELEÇÃO PERMANENTE':
            cleanup.cleanup_all()
        else:
            print("Deleção cancelada.")
            sys.exit(0)


if __name__ == "__main__":
    main()