"""Hide unused fields on sales/purchase transaction doctypes.

Run from the app directory:
	cd ~/frappe-bench-oman/apps/armak
	FRAPPE_API_KEY=... FRAPPE_API_SECRET=... python3 -m armak.hide_transaction_fields
"""

import json
import urllib.parse

from armak.setup_company_data import _get, _get_list, _new, _save

FIELDS = [
	"shipping_rule",
	"scan_barcode",
	"incoterm",
	"time_sheet_list",
	"timesheets",
	"subscription_section",
	"subscription",
	"utm_analytics_section",
	"is_subcontracted",
	"rejected_warehouse",
	"raw_materials_supplied",
	"raw_material_details",
]

DOCTYPES = [
	"Sales Invoice",
	"Sales Order",
	"Delivery Note",
	"Purchase Order",
	"Purchase Invoice",
	"Payment Entry",
]

# fields that live on the item child table rather than the parent form
CHILD_FIELDS = {
	"Sales Invoice Item": ["rejected_warehouse"],
	"Sales Order Item": ["rejected_warehouse"],
	"Delivery Note Item": ["rejected_warehouse"],
	"Purchase Order Item": ["rejected_warehouse"],
	"Purchase Invoice Item": ["rejected_warehouse"],
}


def hide_field(doctype, fieldname):
	existing = _get_list(
		"Property Setter",
		filters=[
			["doc_type", "=", doctype],
			["field_name", "=", fieldname],
			["property", "=", "hidden"],
		],
		fields=["name", "value"],
	)
	if existing:
		doc = _get("Property Setter", existing[0]["name"])
		if doc.get("value") == "1":
			return "unchanged"
		doc["value"] = "1"
		_save("Property Setter", doc)
		return "updated"

	dt_fields = _get_list(
		"DocField",
		filters=[["parent", "=", doctype], ["fieldname", "=", fieldname]],
		fields=["fieldtype"],
	)
	fieldtype = dt_fields[0]["fieldtype"] if dt_fields else "Data"
	_new(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocField",
			"doc_type": doctype,
			"field_name": fieldname,
			"property": "hidden",
			"property_type": fieldtype,
			"value": "1",
		}
	)
	return "created"


def main():
	for doctype in DOCTYPES:
		present = {
			f["fieldname"]
			for f in _get_list(
				"DocField",
				filters=[["parent", "=", doctype], ["fieldname", "in", FIELDS]],
				fields=["fieldname"],
			)
		}
		print(f"== {doctype}")
		for fieldname in FIELDS:
			if fieldname not in present:
				continue
			print(f"  {fieldname}: {hide_field(doctype, fieldname)}")
		missing = sorted(set(FIELDS) - present)
		if missing:
			print(f"  skipped (not on {doctype}): {', '.join(missing)}")

	for doctype, fields in CHILD_FIELDS.items():
		present = {
			f["fieldname"]
			for f in _get_list(
				"DocField",
				filters=[["parent", "=", doctype], ["fieldname", "in", fields]],
				fields=["fieldname"],
			)
		}
		if not present:
			continue
		print(f"== {doctype}")
		for fieldname in fields:
			if fieldname in present:
				print(f"  {fieldname}: {hide_field(doctype, fieldname)}")


def run():
	main()


if __name__ == "__main__":
	run()
