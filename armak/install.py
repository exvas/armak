"""Workshop setup that ships with the app: roles, custom fields and search settings.

Runs on install and on every migrate, so it must stay idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

ROLES = ["Workshop Counter", "Workshop Technician", "Workshop Manager"]

_REPAIR_ORDER_LINK = {
	"fieldname": "armak_repair_order",
	"label": "Repair Order",
	"fieldtype": "Link",
	"options": "Repair Order",
	"read_only": 1,
	"no_copy": 1,
	"search_index": 1,
	"in_standard_filter": 1,
}

CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "armak_civil_id",
			"label": "Civil ID",
			"fieldtype": "Data",
			"unique": 1,
			"in_standard_filter": 1,
			"insert_after": "customer_name",
		},
		{
			"fieldname": "armak_licence_no",
			"label": "Licence No",
			"fieldtype": "Data",
			"insert_after": "armak_civil_id",
		},
	],
	"Sales Invoice": [{**_REPAIR_ORDER_LINK, "insert_after": "customer_name"}],
	"Stock Entry": [{**_REPAIR_ORDER_LINK, "insert_after": "stock_entry_type"}],
	"Payment Entry": [
		{**_REPAIR_ORDER_LINK, "insert_after": "party_name"},
		{
			"fieldname": "armak_payment_stage",
			"label": "Repair Order Payment",
			"fieldtype": "Select",
			"options": "\nAdvance\nBalance",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "armak_repair_order",
			"insert_after": "armak_repair_order",
		},
	],
}


def after_install():
	after_migrate()


def after_migrate():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	create_custom_fields(CUSTOM_FIELDS, update=True)
	# counter staff find returning customers by mobile or Civil ID
	make_property_setter(
		"Customer",
		None,
		"search_fields",
		"customer_name,customer_group,mobile_no,armak_civil_id",
		"Data",
		for_doctype=True,
		validate_fields_for_doctype=False,
	)


def before_tests():
	"""Run ERPNext's test setup (setup wizard, defaults); `run-tests --app armak` only calls our hook."""
	from erpnext.setup.utils import before_tests as erpnext_before_tests

	erpnext_before_tests()
	after_migrate()
	# test setup must survive the per-test rollbacks of the test runner
	frappe.db.commit()  # nosemgrep
