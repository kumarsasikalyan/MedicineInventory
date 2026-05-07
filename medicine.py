import sqlite3
from datetime import date
from fastmcp import FastMCP

# ── Database Setup ────────────────────────────────────────────────────────────

DB_PATH = "medicine_inventory.db"


def get_connection():
    """Create SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def row_to_dict(row):
    """Convert sqlite row to plain dictionary."""
    return {key: row[key] for key in row.keys()}


def init_db():
    """Initialize medicines table."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                quantity INTEGER NOT NULL CHECK(quantity >= 0),
                unit TEXT NOT NULL DEFAULT 'units',
                expiry_date TEXT,
                manufacturer TEXT,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (date('now')),
                updated_at TEXT NOT NULL DEFAULT (date('now'))
            )
        """)
        conn.commit()


# ── MCP Server ────────────────────────────────────────────────────────────────

mcp = FastMCP(name="MedicineInventory")


@mcp.tool()
def add_medicine(
    name: str,
    quantity: int,
    unit: str = "units",
    expiry_date: str | None = None,
    manufacturer: str | None = None,
    description: str | None = None,
):
    """Add a medicine or restock existing medicine."""

    if quantity <= 0:
        return {
            "success": False,
            "error": "Quantity must be greater than zero."
        }

    if expiry_date:
        try:
            date.fromisoformat(expiry_date)
        except ValueError:
            return {
                "success": False,
                "error": "Expiry date must be YYYY-MM-DD."
            }

    try:
        with get_connection() as conn:

            existing = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name)=LOWER(?)",
                (name,)
            ).fetchone()

            if existing:

                conn.execute("""
                    UPDATE medicines
                    SET
                        quantity = quantity + ?,
                        unit = ?,
                        expiry_date = COALESCE(?, expiry_date),
                        manufacturer = COALESCE(?, manufacturer),
                        description = COALESCE(?, description),
                        updated_at = date('now')
                    WHERE id = ?
                """, (
                    quantity,
                    unit,
                    expiry_date,
                    manufacturer,
                    description,
                    existing["id"]
                ))

                action = "restocked"

            else:

                conn.execute("""
                    INSERT INTO medicines
                    (
                        name,
                        quantity,
                        unit,
                        expiry_date,
                        manufacturer,
                        description
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    quantity,
                    unit,
                    expiry_date,
                    manufacturer,
                    description
                ))

                action = "added"

            conn.commit()

            row = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name)=LOWER(?)",
                (name,)
            ).fetchone()

            return {
                "success": True,
                "action": action,
                "medicine": row_to_dict(row)
            }

    except sqlite3.Error as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


@mcp.tool()
def get_medicine(name: str):
    """Get medicine details."""

    try:
        with get_connection() as conn:

            row = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name)=LOWER(?)",
                (name,)
            ).fetchone()

            if not row:
                return {
                    "success": False,
                    "error": f"Medicine '{name}' not found."
                }

            medicine = row_to_dict(row)

            expiry_date = medicine.get("expiry_date")

            if expiry_date:

                days_left = (
                    date.fromisoformat(expiry_date) - date.today()
                ).days

                if days_left < 0:
                    medicine["expiry_status"] = (
                        f"Expired {abs(days_left)} days ago"
                    )

                elif days_left <= 30:
                    medicine["expiry_status"] = (
                        f"Expiring soon ({days_left} days left)"
                    )

                else:
                    medicine["expiry_status"] = (
                        f"Valid ({days_left} days remaining)"
                    )

            return {
                "success": True,
                "medicine": medicine
            }

    except sqlite3.Error as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


@mcp.tool()
def list_medicines(
    only_low_stock: bool = False,
    low_stock_threshold: int = 10
):
    """List medicines from inventory."""

    try:
        with get_connection() as conn:

            if only_low_stock:

                rows = conn.execute("""
                    SELECT *
                    FROM medicines
                    WHERE quantity <= ?
                    ORDER BY quantity ASC
                """, (low_stock_threshold,)).fetchall()

            else:

                rows = conn.execute("""
                    SELECT *
                    FROM medicines
                    ORDER BY name ASC
                """).fetchall()

            medicines = [row_to_dict(row) for row in rows]

            return {
                "success": True,
                "count": len(medicines),
                "medicines": medicines
            }

    except sqlite3.Error as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


@mcp.tool()
def update_quantity(name: str, quantity: int):
    """Update medicine quantity."""

    if quantity < 0:
        return {
            "success": False,
            "error": "Quantity cannot be negative."
        }

    try:
        with get_connection() as conn:

            result = conn.execute("""
                UPDATE medicines
                SET
                    quantity = ?,
                    updated_at = date('now')
                WHERE LOWER(name)=LOWER(?)
            """, (
                quantity,
                name
            ))

            conn.commit()

            if result.rowcount == 0:
                return {
                    "success": False,
                    "error": f"Medicine '{name}' not found."
                }

            row = conn.execute(
                "SELECT * FROM medicines WHERE LOWER(name)=LOWER(?)",
                (name,)
            ).fetchone()

            return {
                "success": True,
                "action": "updated",
                "medicine": row_to_dict(row)
            }

    except sqlite3.Error as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


@mcp.tool()
def delete_medicine(name: str):
    """Delete medicine from inventory."""

    try:
        with get_connection() as conn:

            result = conn.execute(
                "DELETE FROM medicines WHERE LOWER(name)=LOWER(?)",
                (name,)
            )

            conn.commit()

            if result.rowcount == 0:
                return {
                    "success": False,
                    "error": f"Medicine '{name}' not found."
                }

            return {
                "success": True,
                "action": "deleted",
                "name": name
            }

    except sqlite3.Error as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


# ── Main Entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    init_db()

    print("Medicine Inventory MCP SSE server running on port 8000")

    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=8000
    )