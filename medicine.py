import sqlite3
from datetime import date
from typing import Optional
from fastmcp import FastMCP

# ── DB setup ──────────────────────────────────────────────────────────────────

DB_PATH = "medicine_inventory.db"

def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row-factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # lets us access columns by name
    conn.execute("PRAGMA journal_mode=WAL") # safe for concurrent reads
    return conn

def init_db() -> None:
    """Create the medicines table if it doesn't exist yet."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL UNIQUE,
                quantity      INTEGER NOT NULL CHECK(quantity >= 0),
                unit          TEXT    NOT NULL DEFAULT 'units',
                expiry_date   TEXT,           -- stored as ISO-8601 (YYYY-MM-DD)
                manufacturer  TEXT,
                description   TEXT,
                created_at    TEXT    NOT NULL DEFAULT (date('now')),
                updated_at    TEXT    NOT NULL DEFAULT (date('now'))
            )
        """)
        conn.commit()

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(name="MedicineInventory")

@mcp.tool()
def add_medicine(
    name: str,
    quantity: int,
    unit: str = "units",
    expiry_date: Optional[str] = None,
    manufacturer: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Add a new medicine to the inventory or restock an existing one.

    Parameters
    ----------
    name         : Medicine name (case-insensitive unique key).
    quantity     : Number of units to add (must be > 0).
    unit         : Unit of measurement, e.g. 'tablets', 'ml', 'vials'.
    expiry_date  : Expiry date in YYYY-MM-DD format (optional).
    manufacturer : Manufacturer / brand name (optional).
    description  : Any extra notes, dosage info, etc. (optional).

    Returns a dict with the final inventory record.
    """
    if quantity <= 0:
        return {"error": "quantity must be a positive integer."}

    if expiry_date:
        try:
            date.fromisoformat(expiry_date)
        except ValueError:
            return {"error": "expiry_date must be in YYYY-MM-DD format."}

    try:
        with get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE medicines
                    SET quantity     = quantity + ?,
                        unit         = COALESCE(?, unit),
                        expiry_date  = COALESCE(?, expiry_date),
                        manufacturer = COALESCE(?, manufacturer),
                        description  = COALESCE(?, description),
                        updated_at   = date('now')
                    WHERE id = ?
                """, (quantity, unit, expiry_date, manufacturer, description, existing["id"]))
                conn.commit()
                action = "restocked"
            else:
                conn.execute("""
                    INSERT INTO medicines
                        (name, quantity, unit, expiry_date, manufacturer, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, quantity, unit, expiry_date, manufacturer, description))
                conn.commit()
                action = "added"

            row = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()

            return {"status": action, "medicine": dict(row)}

    except sqlite3.Error as e:
        return {"error": f"Database error: {e}"}


@mcp.tool()
def get_medicine(name: str) -> dict:
    """
    Retrieve full details of a medicine by name.

    Parameters
    ----------
    name : Medicine name to look up (case-insensitive).

    Returns the inventory record or an error if not found.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()

        if row is None:
            return {"error": f"Medicine '{name}' not found in inventory."}

        medicine = dict(row)

        if medicine.get("expiry_date"):
            days_left = (date.fromisoformat(medicine["expiry_date"]) - date.today()).days
            if days_left < 0:
                medicine["expiry_status"] = f"EXPIRED {abs(days_left)} days ago"
            elif days_left <= 30:
                medicine["expiry_status"] = f"Expiring soon — {days_left} days left"
            else:
                medicine["expiry_status"] = f"Valid — {days_left} days remaining"

        return {"medicine": medicine}

    except sqlite3.Error as e:
        return {"error": f"Database error: {e}"}


@mcp.tool()
def list_medicines(only_low_stock: bool = False, low_stock_threshold: int = 10) -> dict:
    """
    List all medicines in the inventory.

    Parameters
    ----------
    only_low_stock       : If True, return only medicines with stock below threshold.
    low_stock_threshold  : Quantity threshold for 'low stock' filter (default 10).
    """
    try:
        with get_connection() as conn:
            if only_low_stock:
                rows = conn.execute(
                    "SELECT * FROM medicines WHERE quantity <= ? ORDER BY quantity ASC",
                    (low_stock_threshold,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM medicines ORDER BY name ASC"
                ).fetchall()

        medicines = [dict(r) for r in rows]
        return {"count": len(medicines), "medicines": medicines}

    except sqlite3.Error as e:
        return {"error": f"Database error: {e}"}


@mcp.tool()
def update_quantity(name: str, quantity: int) -> dict:
    """
    Directly set the quantity of an existing medicine (e.g. after a stock-take).

    Parameters
    ----------
    name     : Medicine name (case-insensitive).
    quantity : New absolute quantity (must be >= 0).
    """
    if quantity < 0:
        return {"error": "quantity cannot be negative."}

    try:
        with get_connection() as conn:
            result = conn.execute(
                """
                UPDATE medicines
                SET quantity = ?, updated_at = date('now')
                WHERE LOWER(name) = LOWER(?)
                """,
                (quantity, name),
            )
            conn.commit()

            if result.rowcount == 0:
                return {"error": f"Medicine '{name}' not found."}

            row = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()
            return {"status": "updated", "medicine": dict(row)}

    except sqlite3.Error as e:
        return {"error": f"Database error: {e}"}


@mcp.tool()
def delete_medicine(name: str) -> dict:
    """
    Remove a medicine from the inventory permanently.

    Parameters
    ----------
    name : Medicine name to delete (case-insensitive).
    """
    try:
        with get_connection() as conn:
            result = conn.execute(
                "DELETE FROM medicines WHERE LOWER(name) = LOWER(?)", (name,)
            )
            conn.commit()

        if result.rowcount == 0:
            return {"error": f"Medicine '{name}' not found."}
        return {"status": "deleted", "name": name}

    except sqlite3.Error as e:
        return {"error": f"Database error: {e}"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("Medicine Inventory MCP server starting…")
    mcp.run(transport="sse", host="0.0.0.0", port=8000)