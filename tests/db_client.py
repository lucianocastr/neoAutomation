"""
Cliente SSH → PostgreSQL para la balanza CUORA NEO.
Ejecuta queries via psql remoto — no requiere túnel TCP.
"""

import os
import paramiko
from pathlib import Path
from typing import Optional


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
        self._host    = ssh_host or os.getenv("NEO_SSH_HOST", "192.168.100.123")
        self._user    = ssh_user
        self._key     = ssh_key  or os.getenv("NEO_SSH_KEY_PATH",
                                               str(Path.home() / ".ssh" / "cuora_neo"))
        self._db_user = db_user
        self._db_pass = db_pass or os.getenv("NEO_DB_PASS", "Systel#4316")
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
        """Precio estándar del producto en la lista de precios activa."""
        row = self._one(
            f"SELECT pricestd FROM public.productprice "
            f"WHERE product_id={product_id} AND isactive='Y' LIMIT 1"
        )
        return float(row[0]) if row else None

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
