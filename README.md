# Backend de leads CNPJ

Protótipo backend para consultar estabelecimentos por cidade, UF e CNAE. O piloto começa em Curitiba/PR e supermercados (CNAE `4711302`), mas esses valores são filtros configuráveis da API.

O projeto aceita Python 3.12 a 3.15. No Windows, use uma versão que tenha wheels disponíveis para as dependências.

## Escopo atual

- API FastAPI para consulta paginada de leads já importados.
- DuckDB local como armazenamento de desenvolvimento.
- Importador dos CSVs oficiais da Receita Federal, após extração dos ZIPs.
- Nenhum frontend de produto; a documentação interativa da API fica em `/docs`.

## Preparar o ambiente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Baixar e importar dados

O downloader já vem com o link público do CNPJ da Receita e tenta localizar a pasta mensal automaticamente. Para usar o link padrão, rode:

```powershell
python downloader.py
```

Ele encontra a competência mensal mais recente com os arquivos necessários e baixa apenas CNAEs, municípios, empresas e estabelecimentos. Se a Receita trocar o link público, você pode informar outro com `RF_SHARE_URL`. Para importar os ZIPs:

```powershell
leads-import .\data\source
```

O banco filtrado será criado em `data/leads_rmc.duckdb`. A importação lê os arquivos nacionais, mas grava no DuckDB apenas os estabelecimentos e empresas dos 29 municípios oficiais da Região Metropolitana de Curitiba; os ZIPs originais ficam em `data/source` para permitir reprocessamento. O banco salvo contém a tabela final `leads` e os metadados da carga, sem as tabelas nacionais intermediárias.

## Iniciar a API

```powershell
uvicorn leads_backend.api:app --reload
```

- `GET /health`
- `GET /api/v1/leads?city=CURITIBA&state=PR&cnae=4711302`
- `GET /api/v1/leads?city=CURITIBA&state=PR&cnae=4711302&include_secondary_cnae=true`
- `GET /api/v1/leads?city=CURITIBA&city=COLOMBO&state=PR&cnae=4711302&cnae=4711301`

Os parâmetros `city` e `cnae` aceitam vários valores: repita o parâmetro na URL (`city=CURITIBA&city=COLOMBO`) ou informe valores separados por vírgula (`city=CURITIBA,COLOMBO`). Quando `include_secondary_cnae=true`, qualquer CNAE informado pode corresponder ao principal ou aos secundários. `state` continua sendo uma única UF. Os demais parâmetros são `include_secondary_cnae`, `active_only`, `page` e `page_size` (máximo 500). A API retorna estabelecimentos; redes com várias filiais podem aparecer em mais de uma linha, cada uma com seu próprio CNPJ.

### Acesso com token

O endpoint de leads exige o cabeçalho `X-API-Key`. Configure `LEADS_API_TOKEN` no ambiente antes de iniciar a API. Para testar localmente no CMD, gere um token forte com `python -c "import secrets; print(secrets.token_urlsafe(32))"`, defina-o com `set LEADS_API_TOKEN=SEU_TOKEN` e inicie o servidor no mesmo CMD. Na Vercel, cadastre `LEADS_API_TOKEN` como variável do tipo Secret no projeto e faça um novo deploy. Em `/docs`, use **Authorize** para informar o token. `/health` permanece público.

Não envie o token como parâmetro de URL. Clientes de servidor devem transmiti-lo no cabeçalho `X-API-Key`; não coloque esse segredo diretamente em um frontend público, pois visitantes poderiam extraí-lo.

## Publicar na Vercel

O `index.py` exporta a aplicação FastAPI e `vercel.json` inclui o banco filtrado no pacote da função. O projeto atual usa o repositório `elemdevops-art/api_leads`, branch `main`. O banco `data/leads_rmc.duckdb` é armazenado como arquivo Git normal, não como objeto Git LFS. Depois de cada atualização, valide `/health`, `/docs` e uma consulta em `/api/v1/leads` no domínio da Vercel.

## Fonte e convenções

- Fonte: [Dados Abertos do CNPJ da Receita Federal](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros).
- Layout: [metadados oficiais do CNPJ](https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf).
- O código municipal no arquivo do CNPJ é o código da Receita (Curitiba: `7535`), não o código IBGE. A importação junta a tabela oficial de municípios para expor o nome na consulta.
- O importador preserva CNPJ e CNAEs como texto para manter zeros à esquerda e suportar os formatos alfanuméricos.

## Limitações do protótipo

O primeiro import substitui as tabelas importadas pela competência fornecida. A atualização incremental entre competências e a exposição de informações de origem/data de referência na resposta serão adicionadas numa próxima etapa.
