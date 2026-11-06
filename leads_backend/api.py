import hmac
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi import Security
from fastapi.security import APIKeyHeader

from .config import DEFAULT_CITY, DEFAULT_CNAE, DEFAULT_STATE
from .db import connect, has_leads_table

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="Token de acesso definido em LEADS_API_TOKEN.",
    auto_error=False,
)

app = FastAPI(
    title="Leads API",
    version="0.1.0",
    description="Consulta estabelecimentos do CNPJ por uma ou mais cidades e CNAEs.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    expected_token = os.getenv("LEADS_API_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="A autenticação da API ainda não foi configurada.",
        )
    if not api_key or not hmac.compare_digest(api_key, expected_token):
        raise HTTPException(
            status_code=401,
            detail="Token ausente ou inválido.",
            headers={"WWW-Authenticate": "APIKey"},
        )


@app.get("/api/v1/leads")
def list_leads(
    city: list[str] = Query(
        default=[DEFAULT_CITY],
        description="Uma ou mais cidades. Repita o parâmetro ou separe os nomes por vírgula.",
    ),
    state: str = Query(DEFAULT_STATE, min_length=2, max_length=2),
    cnae: list[str] = Query(
        default=[DEFAULT_CNAE],
        description="Um ou mais CNAEs de 7 dígitos. Repita o parâmetro ou use vírgulas.",
    ),
    include_secondary_cnae: bool = False,
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    _: None = Security(require_api_key),
) -> dict:
    cities = _normalize_values(city, "city", min_length=2, max_length=100)
    cnaes = _normalize_values(cnae, "cnae", min_length=7, max_length=7)

    try:
        connection = connect()
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="Base ainda não foi importada.") from error

    try:
        if not has_leads_table(connection):
            raise HTTPException(status_code=503, detail="Base ainda não foi importada.")

        metadata_row = connection.execute(
            "SELECT source_month, CAST(imported_at AS VARCHAR) "
            "FROM import_metadata LIMIT 1"
        ).fetchone()

        city_placeholders = ", ".join("?" for _ in cities)
        cnae_placeholders = ", ".join("?" for _ in cnaes)
        clauses = [
            f"upper(municipio) IN ({city_placeholders})",
            "upper(uf) = upper(?)",
        ]
        parameters: list[object] = [*cities, state.strip()]
        if active_only:
            clauses.append("situacao_cadastral = '02'")
        if include_secondary_cnae:
            secondary_cnae_clauses = " OR ".join(
                "list_contains(cnae_secundarios, ?)" for _ in cnaes
            )
            clauses.append(
                f"(cnae_principal IN ({cnae_placeholders}) OR {secondary_cnae_clauses})"
            )
            parameters.extend(cnaes)
            parameters.extend(cnaes)
        else:
            clauses.append(f"cnae_principal IN ({cnae_placeholders})")
            parameters.extend(cnaes)

        where_sql = " AND ".join(clauses)
        total = connection.execute(
            f"SELECT count(*) FROM leads WHERE {where_sql}", parameters
        ).fetchone()[0]
        offset = (page - 1) * page_size
        cursor = connection.execute(
            f"SELECT * FROM leads WHERE {where_sql} "
            "ORDER BY razao_social, cnpj LIMIT ? OFFSET ?",
            [*parameters, page_size, offset],
        )
        column_names = [description[0] for description in cursor.description]
        rows = [dict(zip(column_names, row)) for row in cursor.fetchall()]

        return {
            "filters": {
                "city": ",".join(cities),
                "cities": cities,
                "state": state.strip().upper(),
                "cnae": ",".join(cnaes),
                "cnaes": cnaes,
                "include_secondary_cnae": include_secondary_cnae,
                "active_only": active_only,
            },
            "page": page,
            "page_size": page_size,
            "total": total,
            "source_month": metadata_row[0] if metadata_row else None,
            "imported_at": metadata_row[1] if metadata_row and metadata_row[1] else None,
            "items": rows,
        }
    finally:
        connection.close()


def _normalize_values(
    values: list[str], field: str, *, min_length: int, max_length: int
) -> list[str]:
    normalized = list(
        dict.fromkeys(
            part.strip().upper()
            for value in values
            for part in value.split(",")
            if part.strip()
        )
    )
    if not normalized:
        raise HTTPException(status_code=422, detail=f"Informe ao menos um valor para {field}.")
    if any(not min_length <= len(value) <= max_length for value in normalized):
        raise HTTPException(
            status_code=422,
            detail=f"Cada valor de {field} deve ter entre {min_length} e {max_length} caracteres.",
        )
    return normalized
