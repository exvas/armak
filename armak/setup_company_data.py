"""One-off setup: company master data + per-company document naming series.

Source data: docs/Armak_Customer_Information_Form (1).xlsx and the three CR PDFs.
Run from the app directory:
	cd ~/frappe-bench-oman/apps/armak
	FRAPPE_API_KEY=... FRAPPE_API_SECRET=... python3 -m armak.setup_company_data
"""

import json
import os
import urllib.parse

SITE = os.environ.get("ARMAK_SITE", "https://armak.crenya.com")
TIMEOUT = 30


def _headers():
	api_key = os.environ.get("FRAPPE_API_KEY")
	api_secret = os.environ.get("FRAPPE_API_SECRET")
	if not api_key or not api_secret:
		raise SystemExit("Set FRAPPE_API_KEY and FRAPPE_API_SECRET in the environment.")
	return {"Authorization": f"token {api_key}:{api_secret}", "Content-Type": "application/json"}


COMPANIES = {
	"ARMAK TRADING AND CONTRACTING LLC": {
		"company_name": "ARMAK TRADING AND CONTRACTING LLC",
		"abbr": "AT",
		"tax_id": "OM1100073980",
		"phone_no": "93969556",
		"email": "info@armak.om",
		"website": "https://armak.om",
		"date_of_incorporation": "2003-12-06",
		"cr_no": "2189585",
		"vat_pan": "53356",
		"address_line1": "Al Shatri Building",
		"address_line2": "",
		"city": "Salalah",
		"state": "Dhofar Governorate",
		"pincode": "211",
		"po_box": "211",
		"contact_person": "MOHAMMED IBRAHIM",
		"legal_type": "Limited Liability Company",
		"series_abbr": "ARM",
	},
	"Al Sayyad Arabian Trading and Contracting Est": {
		"company_name": "Al Sayyad Arabian Trading and Contracting Est",
		"abbr": "AS",
		"tax_id": "OM1100074043",
		"phone_no": "99494002",
		"email": "Alsayyad.salalah@gmail.com",
		"website": "",
		"date_of_incorporation": "1995-04-05",
		"cr_no": "2097826",
		"vat_pan": "51345",
		"address_line1": "Shop 06, Center Market",
		"address_line2": "",
		"city": "Salalah",
		"state": "Dhofar Governorate",
		"pincode": "211",
		"po_box": "211",
		"contact_person": "MOHAMMED IBRAHIM",
		"legal_type": "Individual Firm / Merchant",
		"series_abbr": "SAY",
	},
	"Al Fajr Oud": {
		"company_name": "Al Fajr Oud",
		"abbr": "AF",
		"tax_id": "",
		"phone_no": "99288020",
		"email": "alfajroud@gmail.com",
		"website": "",
		"date_of_incorporation": "2019-01-07",
		"cr_no": "1334740",
		"vat_pan": "1719343",
		"address_line1": "Shop No 191, Al Haffa New Market",
		"address_line2": "",
		"city": "Salalah",
		"state": "Dhofar Governorate",
		"pincode": "211",
		"po_box": "211",
		"contact_person": "Wadhah Amer",
		"legal_type": "Limited Liability Company",
		"series_abbr": "AFJ",
	},
}

# doctype -> naming series templates using {abbr}
SERIES = {
	"Sales Invoice": ["SINV-{abbr}-.YY.-", "SINV-RET-{abbr}-.YY.-"],
	"Purchase Invoice": ["PINV-{abbr}-.YY.-", "PINV-RET-{abbr}-.YY.-"],
	"Payment Entry": ["PAY-{abbr}-.YY.-"],
	"Journal Entry": ["JV-{abbr}-.YY.-"],
	"Quotation": ["QTN-{abbr}-.YY.-"],
	"Sales Order": ["SO-{abbr}-.YY.-"],
	"Purchase Order": ["PO-{abbr}-.YY.-"],
	"Delivery Note": ["DN-{abbr}-.YY.-", "DN-RET-{abbr}-.YY.-"],
	"Purchase Receipt": ["PREC-{abbr}-.YY.-", "PREC-RET-{abbr}-.YY.-"],
	"Stock Entry": ["STE-{abbr}-.YY.-"],
	"Material Request": ["MR-{abbr}-.YY.-"],
}


def _post(method, payload):
	import urllib.error
	import urllib.request

	req = urllib.request.Request(
		SITE + "/api/method/" + method,
		data=json.dumps(payload).encode(),
		headers=_headers(),
		method="POST",
	)
	try:
		return json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())["message"]
	except urllib.error.HTTPError as e:
		raw = e.read().decode(errors="replace")
		try:
			body = json.loads(raw)
		except json.JSONDecodeError:
			body = {}
		detail = body.get("exception") or body.get("_server_messages") or raw.strip()[:300]
		if e.code in (401, 403):
			detail = f"{detail} (check FRAPPE_API_KEY / FRAPPE_API_SECRET)"
		raise RuntimeError(f"{method} failed: HTTP {e.code} {detail}") from None


def _get_list(doctype, filters=None, fields=("name",), order_by=None):
	payload = {"doctype": doctype, "fields": list(fields), "limit_page_length": 0}
	if filters:
		payload["filters"] = filters
	if order_by:
		payload["order_by"] = order_by
	return _post("frappe.client.get_list", payload)


def _get(doctype, name):
	return _post("frappe.client.get", {"doctype": doctype, "name": name})


def _save(doctype, doc):
	"""Update via REST so the on_update hooks run (deferred linking, currency etc.)."""
	return _post("frappe.client.save", {"doc": doc})


def _new(doc):
	return _post("frappe.client.insert", {"doc": doc})


def _delete(doctype, name):
	import urllib.error
	import urllib.request

	url = f"{SITE}/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name, safe='')}"
	req = urllib.request.Request(url, headers=_headers(), method="DELETE")
	try:
		urllib.request.urlopen(req, timeout=TIMEOUT)
		return True
	except urllib.error.HTTPError as e:
		raise RuntimeError(f"delete {doctype} {name} failed: HTTP {e.code}") from None


def setup_company_master(company, data):
	doc = _get("Company", company)
	updates = {
		"company_name": data["company_name"],
		"tax_id": data["tax_id"],
		"phone_no": data["phone_no"],
		"email": data["email"],
		"website": data["website"] or None,
		"date_of_incorporation": data["date_of_incorporation"],
	}
	changed = {k: v for k, v in updates.items() if doc.get(k) != v}
	if changed:
		doc.update(changed)
		_save("Company", doc)
		print(f"  company updated: {sorted(changed)}")


def setup_address(company, data):
	existing = _get_list(
		"Address",
		filters=[
			["Dynamic Link", "link_doctype", "=", "Company"],
			["Dynamic Link", "link_name", "=", company],
		],
		fields=["name"],
	)
	doc = _get("Address", existing[0]["name"]) if existing else None
	values = {
		"address_title": company,
		"address_type": "Billing",
		"address_line1": data["address_line1"],
		"address_line2": data["address_line2"],
		"city": data["city"],
		"state": data["state"],
		"country": "Oman",
		"pincode": data["pincode"],
		"phone": data["phone_no"],
		"email_id": data["email"],
		"is_primary_address": 1,
		"is_shipping_address": 1,
	}
	if doc:
		changed = {k: v for k, v in values.items() if (doc.get(k) or "") != (v or "")}
		if changed:
			doc.update(changed)
			_save("Address", doc)
			print(f"  address updated: {doc['name']} {sorted(changed)}")
		return doc["name"]

	doc = {"doctype": "Address", "links": [{"link_doctype": "Company", "link_name": company}], **values}
	created = _new(doc)
	print(f"  address created: {created['name']}")
	return created["name"]


def setup_contact(company, data):
	existing = _get_list(
		"Contact",
		filters=[
			["Dynamic Link", "link_doctype", "=", "Company"],
			["Dynamic Link", "link_name", "=", company],
		],
		fields=["name"],
	)
	first, *rest = data["contact_person"].split(" ")
	doc = _get("Contact", existing[0]["name"]) if existing else None
	values = {
		"first_name": first,
		"last_name": " ".join(rest) or None,
		"email_ids": [{"email_id": data["email"], "is_primary": 1}],
		"phone_nos": [{"phone": data["phone_no"], "is_primary_phone": 1, "is_primary_mobile_no": 1}],
	}
	if doc:
		contact_name = doc["name"]
		contact_values = {
			"first_name": first,
			"last_name": " ".join(rest) or None,
			"email_ids": values["email_ids"],
			"phone_nos": values["phone_nos"],
		}
		changed = {}
		if (
			doc.get("first_name") != contact_values["first_name"]
			or doc.get("last_name") != contact_values["last_name"]
		):
			changed.update(
				{"first_name": contact_values["first_name"], "last_name": contact_values["last_name"]}
			)
		if [e.get("email_id") for e in doc.get("email_ids") or []] != [data["email"]]:
			changed["email_ids"] = contact_values["email_ids"]
		if [p.get("phone") for p in doc.get("phone_nos") or []] != [data["phone_no"]]:
			changed["phone_nos"] = contact_values["phone_nos"]
		if changed:
			doc.update(changed)
			_save("Contact", doc)
			print(f"  contact updated: {contact_name} {sorted(changed)}")
		return contact_name

	doc = {"doctype": "Contact", "links": [{"link_doctype": "Company", "link_name": company}], **values}
	created = _new(doc)
	print(f"  contact created: {created['name']}")
	return created["name"]


def set_company_defaults(company, address, contact):
	doc = _get("Company", company)
	if doc.get("default_sales_contact") != contact:
		doc["default_sales_contact"] = contact
		_save("Company", doc)
		print(f"  default sales contact linked: {contact}")
	if not address:
		print("  WARNING: no address linked, company address cannot be defaulted")


def upsert_property_setter(doctype, fieldname, property_, value):
	existing = _get_list(
		"Property Setter",
		filters=[["doc_type", "=", doctype], ["field_name", "=", fieldname], ["property", "=", property_]],
		fields=["name"],
	)
	if existing:
		doc = _get("Property Setter", existing[0]["name"])
		if doc.get("value") == value:
			return "unchanged"
		doc["value"] = value
		_save("Property Setter", doc)
		return "updated"
	_new(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocField",
			"doc_type": doctype,
			"field_name": fieldname,
			"property": property_,
			"property_type": "Text",
			"value": value,
		}
	)
	return "created"


def _company_rules(doctype, company):
	"""Rules are hash-named, so identify ours by doctype + company condition."""
	rules = _get_list(
		"Document Naming Rule",
		filters=[["document_type", "=", doctype]],
		fields=["name", "prefix", "prefix_digits", "disabled"],
	)
	out = []
	for rule in rules:
		doc = _get("Document Naming Rule", rule["name"])
		if any(
			c.get("field") == "company" and c.get("value") == company for c in doc.get("conditions") or []
		):
			out.append(doc)
	return sorted(out, key=lambda d: d["name"])


def upsert_document_naming_rule(doctype, company, prefix, digits=5):
	"""Make `prefix` the automatic naming series for `company` on `doctype`, keeping one rule only."""
	existing = _company_rules(doctype, company)
	if existing:
		keep, *extra = existing
		changed = []
		for field, value in (("prefix", prefix), ("prefix_digits", digits), ("disabled", 0)):
			if keep.get(field) != value:
				keep[field] = value
				changed.append(field)
		if changed:
			_save("Document Naming Rule", keep)
		for doc in extra:
			_delete("Document Naming Rule", doc["name"])
		suffix = f" (+deleted {len(extra)} duplicate)" if extra else ""
		return f"updated {changed}{suffix}" if changed else f"unchanged{suffix}"

	_new(
		{
			"doctype": "Document Naming Rule",
			"document_type": doctype,
			"prefix": prefix,
			"prefix_digits": digits,
			"counter": 0,
			"disabled": 0,
			"conditions": [{"field": "company", "condition": "=", "value": company}],
		}
	)
	return "created"


def main():
	for company, data in COMPANIES.items():
		print(f"== {company}")
		setup_company_master(company, data)
		address = setup_address(company, data)
		contact = setup_contact(company, data)
		set_company_defaults(company, address, contact)

	print("== naming series")
	for doctype, templates in SERIES.items():
		company_series = [
			t.replace("{abbr}", data["series_abbr"]) for data in COMPANIES.values() for t in templates
		]
		existing = _get_list(
			"DocField",
			filters=[["parent", "=", doctype], ["fieldname", "=", "naming_series"]],
			fields=["options"],
		)
		base = [
			line.strip()
			for line in ((existing[0]["options"] if existing else "") or "").splitlines()
			if line.strip()
		]
		# keep framework defaults, drop our own series (current + old .YYYY. form) so re-runs stay stable
		owned = set(company_series) | {line.replace(".YY.", ".YYYY.") for line in company_series}
		lines = [line for line in base if line not in owned]
		seen = set(lines)
		for line in company_series:
			if line not in seen:
				lines.append(line)
				seen.add(line)
		options = "\n".join(lines)
		state = upsert_property_setter(doctype, "naming_series", "options", options)
		first = templates[0].replace("{abbr}", COMPANIES["ARMAK TRADING AND CONTRACTING LLC"]["series_abbr"])
		upsert_property_setter(doctype, "naming_series", "default", first)
		print(f"  {doctype}: options {state} ({len(lines)})")

	print("== document naming rules")
	for doctype, templates in SERIES.items():
		for company, data in COMPANIES.items():
			prefix = templates[0].replace("{abbr}", data["series_abbr"])
			state = upsert_document_naming_rule(doctype, company, prefix)
			print(f"  {doctype} / {company[:34]}: {state} ({prefix})")


def run():
	main()


if __name__ == "__main__":
	run()
