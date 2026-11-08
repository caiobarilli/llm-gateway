# Token em arquivo, relido a cada pedido, fail-closed

## Contexto

O token autoriza o uso da GPU de alguém. Variável de ambiente aparece em `docker inspect` e, no caso do PHParrot, iria para o `terraform.tfstate` em texto (ADR 0013 do PHParrot, item 3). O token também precisa girar sem reiniciar o gateway.

## Decisão

- O token vem de um arquivo (`GATEWAY_TOKEN_ARQUIVO`), montado só leitura pelo consumidor. O arquivo é relido a cada pedido.
- A leitura é em bytes, decodificada como ASCII, com `strip()`.
- Arquivo ausente, ilegível, vazio ou fora de ASCII dá 503 `token_indisponivel`. Nem o token certo passa nesse caso.
- Cabeçalho ausente, malformado ou token errado dá 401 `invalid_api_key`, com `WWW-Authenticate: Bearer` e a mesma mensagem para todo motivo.
- A comparação é `hmac.compare_digest`, nunca `==`.
- A autenticação é dependência do router `/v1`. A única rota fora dele é `/health`, que fica pública por causa do `HEALTHCHECK` da imagem.

## Consequência

- Trocar o token vale no pedido seguinte, sem reiniciar. Custa uma leitura de arquivo por pedido.
- O arquivo precisa ser legível pelo usuário do container (uid 10002).
- O ADR 0013 do PHParrot registra que, num arquivo montado sozinho, trocar o inode (`mv`, editor) deixa o container com o valor antigo, e que a rotação é reescrever o arquivo no lugar. Não foi testado neste repositório.
- Só existe um token. Não há usuário nem escopo por rota.

## Evidência

- `src/llm_gateway/autenticacao.py:14-25` (`ler_token`), `:38-46` (`extrair_bearer`), `:49-51` (`compare_digest`) e `:54-57` (`exigir_token`).
- `src/llm_gateway/app.py:16` (a dependência no router) e `:44-46` (`/health`).
- `tests/test_autenticacao.py:50` (rotação sem reiniciar), `:69`, `:75`, `:81` e `:88` (os quatro casos de 503) e `:94` (sem token no servidor, o token certo não passa).
