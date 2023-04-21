import openai_secret_manager

# Autenticação
secret = openai_secret_manager.get_secret("openai")

# Importando a API GPT-3
import openai
openai.api_key = secret["api_key"]

# Mensagem de entrada
prompt = "Como posso ajudá-lo hoje?"

# Gerando uma resposta com a API GPT-3
response = openai.Completion.create(
    engine="text-davinci-002",
    prompt=prompt,
    max_tokens=2048,
    n = 1,
    stop=None,
    temperature=0.5,
)

# imprimindo a resposta
print(response["choices"][0]["text"])