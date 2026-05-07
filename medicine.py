import sqlite3
from datetime import date
from fastmcp import FastMCP

# ─────────────────────────────────────────────────────────────
# Database Configuration
# ─────────────────────────────────────────────────────────────

DB_PATH = "medicine_inventory.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                quantity INTEGER NOT NULL,

                unit TEXT NOT NULL,

                expiry_date TEXT,

                manufacturer TEXT,

                description TEXT,

                created_at TEXT NOT NULL DEFAULT (date('now')),

                updated_at TEXT NOT NULL DEFAULT (date('now'))

            )
        """)

        conn.commit()


# ─────────────────────────────────────────────────────────────
# MCP Server
# ─────────────────────────────────────────────────────────────

mcp = FastMCP("MedicineInventory")


# ─────────────────────────────────────────────────────────────
# Add Medicine
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def add_medicine(
    name: str,
    quantity: str,
    unit: str,
    expiry_date: str,
    manufacturer: str,
    description: str
):
    """Add or restock medicine."""

    try:

        quantity_int = int(quantity)

        if quantity_int <= 0:
            return {
                "status": "error",
                "message": "Quantity must be greater than zero"
            }

        if expiry_date != "":
            try:
                date.fromisoformat(expiry_date)
            except Exception:
                return {
                    "status": "error",
                    "message": "Expiry date must be YYYY-MM-DD"
                }

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
                        expiry_date = ?,
                        manufacturer = ?,
                        description = ?,
                        updated_at = date('now')
                    WHERE id = ?
                """, (
                    quantity_int,
                    unit,
                    expiry_date,
                    manufacturer,
                    description,
                    existing["id"]
                ))

                conn.commit()

                return {
                    "status": "success",
                    "message": f"{name} restocked successfully"
                }

            else:

                conn.execute("""
                    INSERT INTO medicines (
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
                    quantity_int,
                    unit,
                    expiry_date,
                    manufacturer,
                    description
                ))

                conn.commit()

                return {
                    "status": "success",
                    "message": f"{name} added successfully"
                }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────────────────────
# Get Medicine
# ─────────────────────────────────────────────────────────────

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
                    "status": "error",
                    "message": "Medicine not found"
                }

            expiry_status = "No expiry information"

            if row["expiry_date"]:

                days_left = (
                    date.fromisoformat(row["expiry_date"]) - date.today()
                ).days

                if days_left < 0:
                    expiry_status = f"Expired {abs(days_left)} days ago"

                elif days_left <= 30:
                    expiry_status = f"Expiring in {days_left} days"

                else:
                    expiry_status = f"Valid for {days_left} days"

            message = (
                f"Medicine: {row['name']}, "
                f"Quantity: {row['quantity']} {row['unit']}, "
                f"Manufacturer: {row['manufacturer']}, "
                f"Expiry Status: {expiry_status}"
            )

            return {
                "status": "success",
                "message": message
            }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────────────────────
# List Medicines
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def list_medicines(
    only_low_stock: str,
    low_stock_threshold: str
):
    """List medicines."""

    try:

        low_stock = only_low_stock.lower() == "true"

        threshold = int(low_stock_threshold)

        with get_connection() as conn:

            if low_stock:

                rows = conn.execute("""
                    SELECT *
                    FROM medicines
                    WHERE quantity <= ?
                    ORDER BY quantity ASC
                """, (threshold,)).fetchall()

            else:

                rows = conn.execute("""
                    SELECT *
                    FROM medicines
                    ORDER BY name ASC
                """).fetchall()

            if len(rows) == 0:

                return {
                    "status": "success",
                    "message": "No medicines found"
                }

            medicine_list = []

            for row in rows:

                medicine_list.append(
                    f"{row['name']} ({row['quantity']} {row['unit']})"
                )

            return {
                "status": "success",
                "message": ", ".join(medicine_list)
            }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────────────────────
# Update Quantity
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def update_quantity(
    name: str,
    quantity: str
):
    """Update medicine quantity."""

    try:

        quantity_int = int(quantity)

        if quantity_int < 0:

            return {
                "status": "error",
                "message": "Quantity cannot be negative"
            }

        with get_connection() as conn:

            result = conn.execute("""
                UPDATE medicines
                SET
                    quantity = ?,
                    updated_at = date('now')
                WHERE LOWER(name)=LOWER(?)
            """, (
                quantity_int,
                name
            ))

            conn.commit()

            if result.rowcount == 0:

                return {
                    "status": "error",
                    "message": "Medicine not found"
                }

            return {
                "status": "success",
                "message": f"{name} quantity updated to {quantity_int}"
            }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────────────────────
# Delete Medicine
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def delete_medicine(name: str):
    """Delete medicine."""

    try:

        with get_connection() as conn:

            result = conn.execute(
                "DELETE FROM medicines WHERE LOWER(name)=LOWER(?)",
                (name,)
            )

            conn.commit()

            if result.rowcount == 0:

                return {
                    "status": "error",
                    "message": "Medicine not found"
                }

            return {
                "status": "success",
                "message": f"{name} deleted successfully"
            }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    init_db()

    print("Medicine Inventory MCP SSE Server Running On Port 8000")

    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=8000
    )