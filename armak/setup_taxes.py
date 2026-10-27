"""Create Oman VAT tax setup: accounts, Tax Categories, Item Tax Templates and
Sales/Purchase Taxes and Charges Templates for every company.

Mirrors the naming used by the oman_compliance app (setup/tax_defaults.json) so that
installing it later keeps these documents instead of duplicating them.

Run from the app directory:
	cd ~/frappe-bench-oman/apps/armak
	FRAPPE_API_KEY=... FRAPPE_API_SECRET=... python3 -m armak.setup_taxes
"""

from armak.setup_company_data import COMPANIES, _get, _get_list, _new, _save

# tax categories (title)
TAX_CATEGORIES = ["Standard (S)", "Zero Rated (Z)", "Exempt (E)"]

# account_name -> ledger under Duties and Taxes
VAT_ACCOUNTS = [
	{"account_name": "VAT 5%", "tax_rate": 5.0},
	{"account_name": "VAT Zero", "tax_rate": 0.0},
	{"account_name": "VAT Exempted", "tax_rate": 0.0},
	{"account_name": "VAT Reverse Charge 5%", "tax_rate": 5.0},
]

# Item Tax Template title -> [(account_name, rate)]
ITEM_TAX_TEMPLATES = {
	"Oman VAT 5%": [("VAT 5%", 5.0)],
	"Oman VAT Zero": [("VAT 5%", 0.0), ("VAT Zero", 0.0)],
	"Oman VAT Exempted": [("VAT 5%", 0.0), ("VAT Exempted", 0.0)],
}

# Sales / Purchase template title -> [(account_name, rate, description)]
SALES_TEMPLATES = {
	"Oman VAT 5%": [("VAT 5%", 5.0, "VAT 5%")],
	"Oman VAT Zero": [("VAT Zero", 0.0, "VAT Zero Rated")],
	"Oman VAT Exempted": [("VAT Exempted", 0.0, "VAT Exempted")],
}

PURCHASE_TEMPLATES = {
	"Oman VAT 5%": [("VAT 5%", 5.0, "VAT 5%")],
	"Oman VAT Zero": [("VAT Zero", 0.0, "VAT Zero Rated")],
	"Oman VAT Exempted": [("VAT Exempted", 0.0, "VAT Exempted")],
}


def _tax_parent(company):
	"""Group account that VAT ledgers hang under."""
	parent = _get_list(
		"Account",
		filters=[["company", "=", company], ["account_name", "=", "Duties and Taxes"], ["is_group", "=", 1]],
		fields=["name"],
	)
	if not parent:
		parent = _get_list(
			"Account",
			filters=[["company", "=", company], ["name", "like", "%Duties and Taxes%"], ["is_group", "=", 1]],
			fields=["name"],
		)
	return parent[0]["name"] if parent else None


def ensure_account(company, account_name, tax_rate):
	existing = _get_list(
		"Account",
		filters=[["company", "=", company], ["account_name", "=", account_name], ["is_group", "=", 0]],
		fields=["name"],
	)
	if existing:
		return existing[0]["name"], "unchanged"

	parent = _tax_parent(company)
	if not parent:
		raise RuntimeError(f"No 'Duties and Taxes' group account for {company}")

	created = _new(
		{
			"doctype": "Account",
			"account_name": account_name,
			"company": company,
			"parent_account": parent,
			"is_group": 0,
			"account_type": "Tax",
			"account_currency": "OMR",
			"tax_rate": tax_rate,
		}
	)
	return created["name"], "created"


def ensure_tax_category(title):
	existing = _get_list("Tax Category", filters=[["name", "=", title]], fields=["name"])
	if existing:
		return "unchanged"
	_new({"doctype": "Tax Category", "title": title})
	return "created"


def _tax_account(company, account_name):
	account = _get_list(
		"Account",
		filters=[["company", "=", company], ["account_name", "=", account_name], ["is_group", "=", 0]],
		fields=["name"],
	)
	if not account:
		raise RuntimeError(f"Account {account_name} missing for {company}")
	return account[0]["name"]


def ensure_item_tax_template(company, title, rows):
	existing = _get_list(
		"Item Tax Template", filters=[["title", "=", title], ["company", "=", company]], fields=["name"]
	)
	taxes = [{"tax_type": _tax_account(company, account), "tax_rate": rate} for account, rate in rows]
	if existing:
		doc = _get("Item Tax Template", existing[0]["name"])
		current = [(t["tax_type"], t["tax_rate"]) for t in doc.get("taxes") or []]
		wanted = [(t["tax_type"], t["tax_rate"]) for t in taxes]
		if current == wanted:
			return doc["name"], "unchanged"
		doc["taxes"] = taxes
		_save("Item Tax Template", doc)
		return doc["name"], "updated"

	created = _new(
		{
			"doctype": "Item Tax Template",
			"title": title,
			"company": company,
			"taxes": taxes,
		}
	)
	return created["name"], "created"


def ensure_template(doctype, company, title, rows, tax_category, is_default):
	existing = _get_list(doctype, filters=[["title", "=", title], ["company", "=", company]], fields=["name"])
	taxes = [
		{
			"charge_type": "On Net Total",
			"account_head": _tax_account(company, account),
			"rate": rate,
			"description": description,
		}
		for account, rate, description in rows
	]
	if existing:
		doc = _get(doctype, existing[0]["name"])
		current = [(t["account_head"], t["rate"]) for t in doc.get("taxes") or []]
		wanted = [(t["account_head"], t["rate"]) for t in taxes]
		changed = []
		if current != wanted:
			doc["taxes"] = taxes
			changed.append("taxes")
		if doc.get("tax_category") != tax_category:
			doc["tax_category"] = tax_category
			changed.append("tax_category")
		if changed:
			_save(doctype, doc)
			return doc["name"], f"updated {changed}"
		return doc["name"], "unchanged"

	created = _new(
		{
			"doctype": doctype,
			"title": title,
			"company": company,
			"tax_category": tax_category,
			"is_default": is_default,
			"taxes": taxes,
		}
	)
	return created["name"], "created"


# template title -> linked Tax Category
SALES_CATEGORY = {
	"Oman VAT 5%": "Standard (S)",
	"Oman VAT Zero": "Zero Rated (Z)",
	"Oman VAT Exempted": "Exempt (E)",
}
PURCHASE_CATEGORY = {
	"Oman VAT 5%": "Standard (S)",
	"Oman VAT Zero": "Zero Rated (Z)",
	"Oman VAT Exempted": "Exempt (E)",
}


def main():
	print("== tax categories")
	for title in TAX_CATEGORIES:
		print(f"  {title}: {ensure_tax_category(title)}")

	for company in COMPANIES:
		print(f"== {company}")

		print("  -- VAT accounts")
		for account in VAT_ACCOUNTS:
			_, state = ensure_account(company, account["account_name"], account["tax_rate"])
			print(f"     {account['account_name']}: {state}")

		print("  -- item tax templates")
		for title, rows in ITEM_TAX_TEMPLATES.items():
			_, state = ensure_item_tax_template(company, title, rows)
			print(f"     {title}: {state}")

		print("  -- sales taxes and charges templates")
		for title, rows in SALES_TEMPLATES.items():
			_, state = ensure_template(
				"Sales Taxes and Charges Template",
				company,
				title,
				rows,
				SALES_CATEGORY[title],
				is_default=1 if title == "Oman VAT 5%" else 0,
			)
			print(f"     {title}: {state}")

		print("  -- purchase taxes and charges templates")
		for title, rows in PURCHASE_TEMPLATES.items():
			_, state = ensure_template(
				"Purchase Taxes and Charges Template",
				company,
				title,
				rows,
				PURCHASE_CATEGORY[title],
				is_default=1 if title == "Oman VAT 5%" else 0,
			)
			print(f"     {title}: {state}")


def run():
	main()


if __name__ == "__main__":
	run()
