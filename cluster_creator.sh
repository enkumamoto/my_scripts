#!/bin/bash

#--------------------------------#
# Script para criação de cluster #
#                                #
# Criado por: Eiji Kumamoto Neto #
# Criado em: 26/10/2022          #
# Versão: 0.0.1 - ALPHA          #
#--------------------------------#


echo "Vamos começar a criar um cluster!"
read -p "Mas antes de tudo, sua VPN está ligada? (s/n)" VPN

K2="1.23"

if [ $VPN = s ]; then
  read -p "Informe o nome do novo cluster: " NOME_CLUSTER
  read -p "Informe a região do cluster: " REGIAO
  read -p "Informe a versão do Kubernetes: " KUBERNETES
  read -p "Informe o arn IAM a ser usado: " ARN_IAM
  read -p "Informe a primeira Subnet: " SUBNET1
  read -p "Informe a segunda Subnet: " SUBNET2
  read -p "Informe a terceira Subnet: " SUBNET3
  read -p "Informe a quarta Subnet: " SUBNET4
  read -p "Informe o SecurityGroupIds: " SGIDS

#   else
#   echo "Versão é superior que a suportada pela AWS."
#   done
#   fi
else
echo "Ligue sua VPN e comece novamente."
done
fi

echo "Por favor, aguarde, isto pode demorar..."

aws eks create-cluster --region $REGIAO --name $NOME_CLUSTER --kubernetes-version $KUBERNETES \
--role-arn $ARN_IAM \
--resources-vpc-config subnetIds=$SUBNET1,$SUBNET2,$SUBNET3,$SUBNET4,securityGroupIds=$SGIDS

echo "Habilitando acesso ao Cluster"

aws eks update-kubeconfig --region $REGIAO --name $NOME_CLUSTER

echo "Finalizado."

read -p "Deseja criar um Node Group para o cluster recém criado? (s/n)" NG
if [ $NG = s ]; then
  read -p "Informe o nome do Node Group: " NOME_NG
  read -p "Informe que tipo de instância será usada: " INSTANCIA
  read -p "Informe a quantidade desejavel de Nodes: " DSJ_NODES
  read -p "Informe a quantidade mínima de Nodes: " MIN_NODES
  read -p "Informe a quantidade máxima de Nodes: " MAX_NODES

else
echo "Finalizado o programa"
done
fi

echo "Por favor aguarde, isso pode demorar..."

eksctl create nodegroup \
--cluster $NOME_CLUSTER \
--region $REGIAO \
--name $NOME_NG \
--node-type $INSTANCIA \
--nodes $DSJ_NODES \
--nodes-min $MIN_NODES \
--nodes-max $MAX_NODES \