# Indicador CRM Embapi (SMBOT)

Script usado por uma **rotina do Claude** (roda dia 01) para gerar o indicador mensal
de contatos do CRM (board 8273 do SMBOT) do mês anterior, como painel HTML.

## Uso
```
pip install requests
SMBOT_TOKEN="<jwt do SMBOT>" python3 indicador_crm_cloud.py
```
Gera `indicador_crm_AAAA-MM.html` no diretório atual.

- `SMBOT_TOKEN` = JWT do localStorage `ngStorage-token` do SMBOT (navegador logado). Não expira, mas pode ser revogado — nesse caso o script sai com erro 401 pedindo atualização.
- `REF_MONTH` (opcional) = `AAAA-MM` para reprocessar um mês específico.

Sem segredos versionados. O token entra só por variável de ambiente.
