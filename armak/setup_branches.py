"""One-off setup: Al Sayyad branches, their cost centers and warehouses, the Branch
accounting dimension and Workshop Settings.

Source data: docs/Armak_Customer_Information_Form (1).xlsx (AlSayyad sheet: Branch 1 / Branch 2).
Needs the armak app (Workshop module) installed and migrated on the site first.
Run from the app directory:
	cd ~/frappe-bench-oman/apps/armak
	FRAPPE_API_KEY=... FRAPPE_API_SECRET=... python3 -m armak.setup_branches
"""

from armak.setup_company_data import COMPANIES, _get, _get_list, _new, _save

COMPANY = "Al Sayyad Arabian Trading and Contracting Est"
ABBR = COMPANIES[COMPANY]["abbr"]

# branch -> warehouses kept at that branch; the first "materials" one feeds Repair Orders
BRANCHES = {
	"Center Market": {
		"description": "Retail Shop - Center Market",
		"warehouses": ["Center Market Showroom"],
		"materials_warehouse": None,
	},
	"Awqad Industrial": {
		"description": "Service & Retail - Awqad Industrial",
		"warehouses": ["Awqad Showroom", "Awqad Workshop Materials", "Awqad Production Materials"],
		"materials_warehouse": "Awqad Workshop Materials",
	},
}
DEFAULT_BRANCH = "Awqad Industrial"


def setup_branch(branch):
	if _get_list("Branch", filters=[["name", "=", branch]]):
		return "unchanged"
	_new({"doctype": "Branch", "branch": branch})
	return "created"


def setup_cost_center(branch):
	name = f"{branch} - {ABBR}"
	if _get_list("Cost Center", filters=[["name", "=", name]]):
		return name, "unchanged"
	parent = _get_list(
		"Cost Center",
		filters=[["company", "=", COMPANY], ["is_group", "=", 1], ["parent_cost_center", "in", ["", None]]],
	)
	if not parent:
		raise SystemExit(f"No root cost center found for {COMPANY}")
	_new(
		{
			"doctype": "Cost Center",
			"cost_center_name": branch,
			"company": COMPANY,
			"parent_cost_center": parent[0]["name"],
			"is_group": 0,
		}
	)
	return name, "created"


def setup_warehouse(warehouse):
	name = f"{warehouse} - {ABBR}"
	if _get_list("Warehouse", filters=[["name", "=", name]]):
		return name, "unchanged"
	_new(
		{
			"doctype": "Warehouse",
			"warehouse_name": warehouse,
			"company": COMPANY,
			"parent_warehouse": f"All Warehouses - {ABBR}",
			"is_group": 0,
		}
	)
	return name, "created"


def setup_accounting_dimension():
	"""Branch on invoices, payments, stock entries and the GL, so every report can split by branch."""
	if _get_list("Accounting Dimension", filters=[["document_type", "=", "Branch"]]):
		return "unchanged"
	_new({"doctype": "Accounting Dimension", "document_type": "Branch", "label": "Branch"})
	return "created (fields are added to the transaction doctypes by a background job)"


def setup_workshop_settings(rows):
	doc = _get("Workshop Settings", "Workshop Settings")
	current = [
		(r.get("branch"), r.get("materials_warehouse"), r.get("cost_center"))
		for r in doc.get("branches") or []
	]
	wanted = [(r["branch"], r["materials_warehouse"], r["cost_center"]) for r in rows]
	changed = []
	if current != wanted:
		doc["branches"] = [{"doctype": "Workshop Branch", "company": COMPANY, **r} for r in rows]
		changed.append("branches")
	if doc.get("default_branch") != DEFAULT_BRANCH:
		doc["default_branch"] = DEFAULT_BRANCH
		changed.append("default_branch")
	if changed:
		_save("Workshop Settings", doc)
	return f"updated {changed}" if changed else "unchanged"


def main():
	print(f"== branches of {COMPANY}")
	rows = []
	for branch, data in BRANCHES.items():
		print(f"  branch {branch}: {setup_branch(branch)}")
		cost_center, state = setup_cost_center(branch)
		print(f"    cost center {cost_center}: {state}")
		for warehouse in data["warehouses"]:
			name, state = setup_warehouse(warehouse)
			print(f"    warehouse {name}: {state}")
		if data["materials_warehouse"]:
			rows.append(
				{
					"branch": branch,
					"materials_warehouse": f"{data['materials_warehouse']} - {ABBR}",
					"cost_center": cost_center,
				}
			)

	print(f"== accounting dimension Branch: {setup_accounting_dimension()}")
	print(f"== workshop settings: {setup_workshop_settings(rows)}")


def run():
	main()


if __name__ == "__main__":
	run()
