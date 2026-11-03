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
	"""Complete the ERPNext setup wizard on a fresh test site; `run-tests --app armak` only calls our hook.

	v15 ships `erpnext.setup.utils.before_tests`; v16 removed it, so the same steps are done here.
	"""
	try:
		from erpnext.setup.utils import before_tests as erpnext_before_tests
	except ImportError:
		erpnext_before_tests = _erpnext_before_tests

	erpnext_before_tests()
	after_migrate()
	# test setup must survive the per-test rollbacks of the test runner
	frappe.db.commit()  # nosemgrep


def _erpnext_before_tests():
	from erpnext.setup.utils import _enable_all_roles_for_admin, set_defaults_for_tests
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
	from frappe.utils import now_datetime

	frappe.clear_cache()
	if not frappe.db.a_row_exists("Company"):
		year = now_datetime().year
		setup_complete(
			{
				"currency": "USD",
				"full_name": "Test User",
				"company_name": "Wind Power LLC",
				"timezone": "America/New_York",
				"company_abbr": "WP",
				"industry": "Manufacturing",
				"country": "United States",
				"fy_start_date": f"{year}-01-01",
				"fy_end_date": f"{year}-12-31",
				"language": "english",
				"company_tagline": "Testing",
				"email": "test@erpnext.com",
				"password": "test",
				"chart_of_accounts": "Standard",
			}
		)
	frappe.db.sql("delete from `tabItem Price`")
	_enable_all_roles_for_admin()
	set_defaults_for_tests()
