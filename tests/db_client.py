"""
Cliente SSH → PostgreSQL para la balanza CUORA NEO.
Ejecuta queries via psql remoto — no requiere túnel TCP.
"""

import os
import paramiko
from pathlib import Path
from typing import Optional


def _require_env(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise RuntimeError(
            f"Variable de entorno requerida no definida: {var}\n"
            f"Copiar .env.test.example a .env.test y completar los valores."
        )
    return val


class BalanzaDB:
    def __init__(
        self,
        ssh_host: str = None,
        ssh_user: str = "root",
        ssh_key:  str = None,
        db_user:  str = "systel",
        db_pass:  str = None,
        db_name:  str = "cuora",
    ):
        self._host    = ssh_host or _require_env("NEO_SSH_HOST")
        self._user    = ssh_user
        self._key     = ssh_key  or os.getenv("NEO_SSH_KEY_PATH",
                                               str(Path.home() / ".ssh" / "cuora_neo"))
        self._db_user = db_user
        self._db_pass = db_pass or _require_env("NEO_DB_PASS")
        self._db_name = db_name

    # ── Queries tipadas ──────────────────────────────────────────

    def invoice_count(self) -> int:
        row = self._one("SELECT COUNT(*) FROM public.invoice")
        return int(row[0]) if row else 0

    def latest_sale(self) -> Optional[dict]:
        """Retorna la última venta con su línea de producto."""
        row = self._one("""
            SELECT i.invoice_id, i.documentno, i.grandtotal,
                   il.product_id, il.qtyinvoiced, il.priceactual, il.linenetamt,
                   il.tare, p.name
            FROM public.invoice i
            JOIN public.invoiceline il ON il.invoice_id = i.invoice_id
            LEFT JOIN public.product  p  ON p.product_id = il.product_id
            ORDER BY i.created DESC
            LIMIT 1
        """)
        if not row:
            return None
        return {
            "invoice_id":   row[0],
            "documentno":   row[1],
            "grandtotal":   float(row[2]),
            "product_id":   int(row[3]) if row[3] else None,
            "qty_kg":       float(row[4]),
            "price_per_kg": float(row[5]),
            "line_total":   float(row[6]),
            "tare_kg":      float(row[7]),
            "product_name": row[8],
        }

    def product_price(self, product_id: int) -> Optional[float]:
        """Precio de Lista 1 desde productprice (columna 'pricelist', version 'lst1')."""
        row = self._one(
            f"SELECT pricelist FROM public.productprice "
            f"WHERE product_id={product_id} "
            f"AND pricelist_version_id='lst1' AND isactive='Y' "
            f"LIMIT 1"
        )
        return float(row[0]) if row else None

    def product_detail(self, plu_id: int) -> Optional[dict]:
        """Campos clave del producto directo desde PostgreSQL — para tests de integridad."""
        row = self._one(
            f"SELECT name, uom_id, extra_field2, preservation_info, "
            f"ingredients, extra_field1, upc, isactive "
            f"FROM public.product WHERE product_id={plu_id}"
        )
        if not row:
            return None
        keys = ["name", "uom_id", "extra_field2", "preservation_info",
                "ingredients", "extra_field1", "upc", "isactive"]
        return dict(zip(keys, row))

    def advertising_detail(self, name: str) -> Optional[dict]:
        """Fila de advertising por nombre — para tests de integridad."""
        safe = name.replace("'", "''")
        row = self._one(
            f"SELECT name, advertising, isactive "
            f"FROM public.advertising WHERE name='{safe}' "
            f"ORDER BY created DESC LIMIT 1"
        )
        if not row:
            return None
        return {"name": row[0], "text": row[1], "isactive": row[2]}

    def get_setup_param(self, param_id: str) -> Optional[dict]:
        """Valor de un parámetro de public.setup por su id."""
        safe = param_id.replace("'", "''")
        row = self._one(
            f"SELECT param, value_int, value_string, value_double "
            f"FROM public.setup WHERE id='{safe}'"
        )
        if not row:
            return None
        return {
            "param":    row[0],
            "value_int": int(row[1]) if row[1] not in (None, "") else None,
            "value_str": row[2],
            "value_dbl": float(row[3]) if row[3] not in (None, "") else None,
        }

    def saves_invoices(self) -> bool:
        """True si la balanza está configurada para guardar ventas en invoice.
        saveinvoice.value_int=1 → guarda; 0 → NO guarda (modo etiqueta sin registro).
        Nota: el modo ticket/etiqueta NO vive en public.setup — es estado en memoria
        de la aplicación. Este flag solo refleja la configuración de guardado."""
        p = self.get_setup_param("saveinvoice")
        return bool(p and p["value_int"] == 1) if p else False

    def active_products(self) -> list[dict]:
        """Lista de productos activos con precio."""
        rows = self._all("""
            SELECT DISTINCT p.product_id, p.name, pp.pricestd
            FROM public.product p
            JOIN public.productprice pp ON pp.product_id = p.product_id
            WHERE p.isactive='Y' AND pp.isactive='Y'
            ORDER BY p.product_id
        """)
        return [{"id": int(r[0]), "name": r[1], "price": float(r[2])} for r in rows]

    # ── Infraestructura ──────────────────────────────────────────

    def _run(self, sql: str) -> str:
        sql_clean = sql.replace('"', '\\"').replace('\n', ' ').strip()
        cmd = (
            f'PGPASSWORD="{self._db_pass}" psql -U {self._db_user} '
            f'-d {self._db_name} -t -A -F"|" -c "{sql_clean}"'
        )
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            pkey = paramiko.Ed25519Key.from_private_key_file(
                os.path.expanduser(self._key)
            )
            client.connect(self._host, username=self._user, pkey=pkey, timeout=10)
            _, stdout, _ = client.exec_command(cmd)
            return stdout.read().decode("utf-8", errors="replace").strip()
        finally:
            client.close()

    def _one(self, sql: str) -> Optional[list]:
        raw = self._run(sql)
        if not raw:
            return None
        return raw.splitlines()[0].split("|")

    def _all(self, sql: str) -> list:
        raw = self._run(sql)
        if not raw:
            return []
        return [line.split("|") for line in raw.splitlines() if line.strip()]
