# Leitor de Diários Oficiais

Servidor MCP remoto, somente de leitura, para ajudar o ChatGPT a consultar documentos
oficiais do DOU, DOE-PA, gov.br e Diário Oficial do Município de Belém.

## O que ele faz

- baixa documentos oficiais com cinco tentativas e timeout ampliado;
- recusa URLs fora dos domínios oficiais autorizados;
- valida a assinatura `%PDF-` e calcula SHA-256;
- informa quantidade de páginas e metadados;
- extrai intervalos de páginas;
- pesquisa termos e devolve página e trecho;
- verifica URLs previsíveis das edições regular e extra do DOE-PA;
- gera links oficiais das Seções 1, 2 e 3 do DOU.

## Publicar no Render

1. Crie uma conta em https://github.com e um repositório vazio chamado
   `leitor-diarios-oficiais`.
2. Envie todos os arquivos desta pasta para o repositório.
3. Crie uma conta em https://render.com usando a conta do GitHub.
4. No Render, escolha `New` e depois `Blueprint`.
5. Selecione o repositório `leitor-diarios-oficiais`.
6. Confirme a criação. O arquivo `render.yaml` fornece os comandos necessários.
7. Aguarde o status `Live`.
8. Abra `https://SEU-ENDERECO.onrender.com/health`. A resposta esperada é:

   ```json
   {"status":"ok","service":"leitor-diarios-oficiais"}
   ```

9. O endpoint MCP será `https://SEU-ENDERECO.onrender.com/mcp`.

O arquivo começa no plano gratuito para permitir o teste sem cobrança. Esse plano pode
levar cerca de um minuto para despertar após 15 minutos sem uso. Para uma rotina diária
confiável, altere depois o serviço para uma instância paga que não seja suspensa por inatividade.

## Conectar ao ChatGPT

O administrador precisa habilitar `Developer mode / Create custom MCP connectors`.
Depois:

1. Abra o ChatGPT na versão web.
2. Acesse `Settings` > `Apps & Connectors`.
3. Escolha `Create`.
4. Informe o nome `Leitor de Diários Oficiais`.
5. Informe a URL `https://SEU-ENDERECO.onrender.com/mcp`.
6. Escolha `No authentication` para o primeiro teste.
7. Clique em `Scan tools` e confira as cinco ferramentas.
8. Clique em `Create`.
9. Após os testes, peça ao administrador para publicar a aplicação e autorizá-la no
   agente `Monitor Ambiental dos Diários`.

## Teste local opcional

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest -v test_core.py
uvicorn server:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```bash
curl http://127.0.0.1:8000/health
```

## Limitações conhecidas

- Alguns portais podem bloquear endereços de datacenters, mesmo fora do ChatGPT.
- Páginas que exigem JavaScript podem precisar de uma futura integração com navegador.
- O servidor não interpreta juridicamente os atos; ele apenas recupera e extrai evidências.
- A primeira versão não usa autenticação. Antes de uso amplo, recomenda-se autenticação
  e limites de requisição.
