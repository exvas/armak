"""Create Client Scripts that hide unused fields on transaction forms.

Run from the app directory:
	cd ~/frappe-bench-oman/apps/armak
	FRAPPE_API_KEY=... FRAPPE_API_SECRET=... python3 -m armak.hide_fields_client_script
"""

from armak.setup_company_data import _get, _get_list, _new, _save

# doctype -> fields to hide
HIDE = {
	"Sales Invoice": [
		"shipping_rule",
		"scan_barcode",
		"incoterm",
		"time_sheet_list",
		"timesheets",
		"subscription_section",
		"subscription",
		"utm_analytics_section",
	],
	"Sales Order": [
		"shipping_rule",
		"scan_barcode",
		"incoterm",
		"utm_analytics_section",
		"has_subcontracting",
		"is_subcontracted",
	],
	"Delivery Note": [
		"shipping_rule",
		"scan_barcode",
		"incoterm",
		"utm_analytics_section",
	],
	"Purchase Order": [
		"shipping_rule",
		"scan_barcode",
		"incoterm",
		"is_subcontracted",
		"is_old_subcontracting_flow",
		"raw_material_details",
	],
	"Purchase Invoice": [
		"shipping_rule",
		"scan_barcode",
		"incoterm",
		"subscription_section",
		"subscription",
		"is_subcontracted",
		"is_old_subcontracting_flow",
		"rejected_warehouse",
		"raw_materials_supplied",
	],
	"Payment Entry": [
		"shipping_rule",
		"scan_barcode",
		"incoterm",
		"time_sheet_list",
		"timesheets",
		"subscription_section",
		"subscription",
		"utm_analytics_section",
		"has_subcontracting",
		"is_subcontracted",
		"is_old_subcontracting_flow",
		"rejected_warehouse",
		"raw_materials_supplied",
		"raw_material_details",
	],
}

SCRIPT_TEMPLATE = """frappe.ui.form.on("{doctype}", {{
	refresh(frm) {{
		{fields}.forEach((fieldname) => frm.set_df_property(fieldname, "hidden", 1));
	}},
}});
"""


def script_name(doctype):
	return f"Hide unused fields - {doctype}"


def build_script(doctype, fields):
	field_list = "[" + ", ".join(f'"{f}"' for f in fields) + "]"
	return SCRIPT_TEMPLATE.format(doctype=doctype, fields=field_list)


def upsert_client_script(doctype, fields):
	name = script_name(doctype)
	script = build_script(doctype, fields)
	existing = _get_list("Client Script", filters=[["name", "=", name]], fields=["name"])

	if existing:
		doc = _get("Client Script", name)
		changed = []
		if doc.get("script") != script:
			doc["script"] = script
			changed.append("script")
		if doc.get("enabled") != 1:
			doc["enabled"] = 1
			changed.append("enabled")
		if changed:
			_save("Client Script", doc)
			return f"updated {changed}"
		return "unchanged"

	_new(
		{
			"doctype": "Client Script",
			"name": name,
			"dt": doctype,
			"view": "Form",
			"enabled": 1,
			"script": script,
		}
	)
	return "created"


def main():
	for doctype, fields in HIDE.items():
		present = {
			f["fieldname"]
			for f in _get_list(
				"DocField",
				filters=[["parent", "=", doctype], ["fieldname", "in", fields]],
				fields=["fieldname"],
			)
		}
		print(f"== {doctype}: {upsert_client_script(doctype, fields)}")
		print(f"   present: {sorted(present) or 'none'}")
		missing = sorted(set(fields) - present)
		if missing:
			print(f"   absent (no-op, kept for future): {missing}")


def run():
	main()


if __name__ == "__main__":
	run()
