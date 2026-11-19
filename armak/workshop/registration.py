"""Customer and gun registration at the counter.

The workshop identifies a customer by mobile number (the client's Customer ID); the Civil ID is
optional. Staff look a customer up by mobile or gun number, or register both in one step.
"""

import re

import frappe
from frappe import _

COUNTRY_CODE = "968"


def mobile_digits(mobile):
	"""Digits of `mobile` with the Oman country code: '9123 4567', '+968 91234567' -> '96891234567'."""
	digits = re.sub(r"\D", "", mobile or "")
	if digits.startswith("00"):
		digits = digits[2:]
	if len(digits) == 8:
		digits = COUNTRY_CODE + digits
	return digits


def find_customer_by_mobile(mobile, exclude=None):
	"""The enabled customer whose mobile has the same digits, however it was typed."""
	digits = mobile_digits(mobile)
	if not digits:
		return None
	local = digits[len(COUNTRY_CODE) :] if digits.startswith(COUNTRY_CODE) else digits
	rows = frappe.db.sql(
		"""
		select name from `tabCustomer`
		where disabled = 0 and ifnull(mobile_no, '') != '' and name != %(exclude)s
			and regexp_replace(mobile_no, '[^0-9]', '') in (%(digits)s, %(local)s, %(intl)s)
		order by creation
		limit 1
		""",
		{"digits": digits, "local": local, "intl": "00" + digits, "exclude": exclude or ""},
	)
	return rows[0][0] if rows else None


def customer_validate(doc, method=None):
	"""Customer hook: a mobile number already used by another customer is flagged, not refused,
	because other companies on the site may share a switchboard number."""
	if doc.mobile_no and (other := find_customer_by_mobile(doc.mobile_no, exclude=doc.name)):
		frappe.msgprint(
			_("Mobile {0} is already the Customer ID of {1}").format(doc.mobile_no, other),
			indicator="orange",
			alert=True,
		)


@frappe.whitelist()
def lookup(mobile: str | None = None, gun_number: str | None = None):
	"""The customer and guns for a mobile number or a gun number, for the counter dialog."""
	frappe.has_permission("Repair Order", "create", throw=True)
	customer = None
	if gun_number:
		customer = frappe.db.get_value("Gun", normalize_gun_number(gun_number), "customer")
	if not customer and mobile:
		customer = find_customer_by_mobile(mobile)
	if not customer:
		return {}
	details = frappe.db.get_value(
		"Customer",
		customer,
		["name", "customer_name", "mobile_no", "armak_civil_id", "armak_licence_no"],
		as_dict=True,
	)
	details.guns = frappe.get_all(
		"Gun",
		filters={"customer": customer, "disabled": 0},
		fields=["name", "gun_type", "make", "licence_no"],
		order_by="creation desc",
	)
	return details


@frappe.whitelist()
def register(
	mobile: str,
	customer_name: str | None = None,
	gun_number: str | None = None,
	civil_id: str | None = None,
	licence_no: str | None = None,
	gun_type: str | None = None,
	make: str | None = None,
):
	"""Find the customer by mobile or register them, then find or register the gun.

	Returns {customer, gun}. A gun registered to another customer is refused, not moved.
	"""
	frappe.has_permission("Repair Order", "create", throw=True)
	if not mobile_digits(mobile):
		frappe.throw(_("Enter the customer's mobile number"))

	customer = find_customer_by_mobile(mobile)
	if not customer:
		if not (customer_name or "").strip():
			frappe.throw(_("Enter the name of the new customer"))
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": customer_name.strip(),
				"customer_type": "Individual",
				"customer_group": default_customer_group(),
				"territory": default_territory(),
				"mobile_no": mobile.strip(),
				"armak_civil_id": (civil_id or "").strip() or None,
				"armak_licence_no": (licence_no or "").strip() or None,
			}
		).insert()
		customer = doc.name
	else:
		# fill in an ID or licence the customer did not have before
		updates = {}
		current = frappe.db.get_value(
			"Customer", customer, ["armak_civil_id", "armak_licence_no"], as_dict=True
		)
		if civil_id and not current.armak_civil_id:
			updates["armak_civil_id"] = civil_id.strip()
		if licence_no and not current.armak_licence_no:
			updates["armak_licence_no"] = licence_no.strip()
		if updates:
			doc = frappe.get_doc("Customer", customer)
			doc.update(updates)
			doc.save()

	gun = None
	if gun_number:
		gun = normalize_gun_number(gun_number)
		owner = frappe.db.get_value("Gun", gun, "customer")
		if owner and owner != customer:
			frappe.throw(
				_("Gun {0} is registered to {1}. Change the gun's owner on the Gun record first.").format(
					gun, frappe.db.get_value("Customer", owner, "customer_name")
				)
			)
		if not owner:
			gun = (
				frappe.get_doc(
					{
						"doctype": "Gun",
						"gun_number": gun,
						"customer": customer,
						"gun_type": gun_type,
						"make": make,
						"licence_no": licence_no,
					}
				)
				.insert()
				.name
			)
	return {"customer": customer, "gun": gun}


def normalize_gun_number(gun_number):
	return " ".join((gun_number or "").split()).upper()


def default_customer_group():
	group = frappe.db.get_single_value("Selling Settings", "customer_group")
	if group and not frappe.db.get_value("Customer Group", group, "is_group"):
		return group
	return frappe.db.get_value("Customer Group", {"is_group": 0}, "name", order_by="lft")


def default_territory():
	territory = frappe.db.get_single_value("Selling Settings", "territory")
	if territory and not frappe.db.get_value("Territory", territory, "is_group"):
		return territory
	return frappe.db.get_value("Territory", {"is_group": 0}, "name", order_by="lft") or territory
