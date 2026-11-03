from frappe import _


def get_data():
	return {
		"fieldname": "gun",
		"transactions": [{"label": _("Workshop"), "items": ["Repair Order"]}],
	}
