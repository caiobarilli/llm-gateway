---
name: pytest-gateway
description: Como testar o llm-gateway com pytest — app pela factory com o Ollama falso (httpx MockTransport), nenhum acesso à rede, testes que provam que segredo e texto não vão para o log, concorrência, contrato com o SDK da OpenAI e cobertura. Use ao escrever ou revisar testes, ao corrigir bug (teste primeiro) ou ao conferir a cobertura.
---

# pytest no llm-gateway

Os testes provam o comportamento do gateway sem modelo, sem rede e sem token
real. Se um teste precisa do Ollama de verdade, ele não é deste repositório:
a prova de ponta a ponta mora no consumidor (o grupo `ollama` do PHParrot).

## 1. Fixtures (tests/conftest.py)

- `config`: `Config` montado à mão, com o token num arquivo em `tmp_path`,
  um modelo permitido e concorrência 1.
- `ollama`: o `OllamaFalso`, que guarda os pedidos recebidos e responde o que
  o teste mandar (`responder_com(...)` ou um `responder` assíncrono próprio).
- `app` e `cliente`: `criar_app(config, httpx2.MockTransport(ollama))` dentro
  de um `TestClient`. Nunca suba uvicorn nem abra porta.
- Reaproveite as fixtures. Fixture nova só quando duas ou mais suítes precisam.

## 2. O que todo comportamento novo precisa provar

- O caminho feliz e cada recusa, com o status e o `code` exatos do erro.
- O que chegou ao Ollama (`ollama.pedidos`): caminho, modelo e corpo. Recusa
  não pode chegar ao upstream; o teste confere que `ollama.pedidos` ficou vazio.
- A linha de métricas daquele pedido (`caplog`, logger do módulo) com o
  conjunto exato de campos.

## 3. Segredo e texto fora do log

Essas provas já existem e não podem ser enfraquecidas:

- `test_token_nao_aparece_no_log_nem_na_resposta`
- `test_prompt_resposta_schema_e_token_nunca_vao_para_o_log`

Regras:

- Use valores marcados (`SAIDA_SECRETA`, `PROMPT`, um token fixo) e confira
  que nenhum aparece em `caplog.text` nem na saída capturada (`capfd`).
- Campo novo no log ou nova mensagem de erro: acrescente o valor marcado à
  lista do teste correspondente.
- Logue em `DEBUG` nesses testes, para pegar vazamento em qualquer nível.

## 4. Concorrência

- O limite é provado com dois pedidos ao mesmo tempo: um responde 200, o outro
  503 `ocupado` com `Retry-After`. Use um upstream falso que segura a resposta
  até o teste liberar; nunca `sleep`.
- A vaga precisa voltar depois de erro do upstream: teste o caso.

## 5. Contrato com a OpenAI

- Um teste usa o SDK oficial `openai` (dependência só de dev, versão exata)
  apontado para o app, e confere `chat.completions.create` e `models.list`.
  É a prova de que "compatível com a OpenAI" é verdade, não promessa.

## 6. MCP

- As ferramentas são testadas com o cliente em memória do FastMCP
  (`Client(mcp)`): sem token recusa, modelo fora da allowlist recusa,
  ocupado responde ocupado, e a linha de métricas sai sem texto.

## 7. Cobertura

- `pytest --cov=llm_gateway --cov-report=term-missing` no estágio `teste`.
- O piso fica no `pyproject.toml` (`fail_under`). Ele só sobe.
- Linha descoberta se resolve com teste do comportamento, não com
  `pragma: no cover`. `no cover` só em código que não existe em runtime.

## 8. Bug: teste primeiro

1. Escreva o teste que reproduz o bug e veja falhar.
2. Corrija.
3. Veja passar e registre o caso em `.ai/pitfalls.md` com a evidência
   (commit e `arquivo:linha`).

## Checklist de revisão

- [ ] Nenhum teste acessa rede, disco fora de `tmp_path` ou relógio real.
- [ ] Toda recusa confere status, `code` e que o upstream não foi chamado.
- [ ] Campo novo de log tem prova de que não carrega texto nem segredo.
- [ ] Cobertura não caiu.
