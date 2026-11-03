"""Data for the Workshop workspace number cards and the Workshop Board page."""

import frappe
from frappe.utils import flt, get_datetime, getdate, now_datetime, nowdate

OPEN_STATUSES = ("Received", "In Progress", "Ready for Delivery")
WORKING_STATUSES = ("Received", "In Progress")


def _branch_filters(branch=None):
	filters = {"docstatus": 1}
	if branch:
		filters["branch"] = branch
	return filters


def _count(**filters):
	return frappe.db.count("Repair Order", filters) if frappe.has_permission("Repair Order") else 0


def _card(value, fieldtype="Int"):
	return {"value": value, "fieldtype": fieldtype}


# ------------------------------------------------------------ number cards


@frappe.whitelist()
def open_orders(filters: str | dict | list | None = None):
	return _card(_count(docstatus=1, status=("in", WORKING_STATUSES)))


@frappe.whitelist()
def ready_for_delivery(filters: str | dict | list | None = None):
	return _card(_count(docstatus=1, status="Ready for Delivery"))


@frappe.whitelist()
def late_orders(filters: str | dict | list | None = None):
	return _card(
		_count(docstatus=1, status=("in", WORKING_STATUSES), expected_delivery=("<", now_datetime()))
	)


@frappe.whitelist()
def todays_collections(filters: str | dict | list | None = None):
	"""Advances and balances taken on Repair Orders today."""
	if not frappe.has_permission("Payment Entry"):
		return _card(0, "Currency")
	amounts = frappe.get_list(
		"Payment Entry",
		filters={"docstatus": 1, "posting_date": nowdate(), "armak_repair_order": ("is", "set")},
		pluck="base_paid_amount",
		limit_page_length=0,
	)
	return _card(sum(flt(a) for a in amounts), "Currency")


@frappe.whitelist()
def unpaid_balance(filters: str | dict | list | None = None):
	"""Balance still to collect on open orders (advances deducted)."""
	if not frappe.has_permission("Repair Order"):
		return _card(0, "Currency")
	balances = frappe.get_list(
		"Repair Order",
		filters={"docstatus": 1, "status": ("in", OPEN_STATUSES)},
		pluck="balance",
		limit_page_length=0,
	)
	return _card(sum(flt(b) for b in balances), "Currency")


@frappe.whitelist()
def low_stock_items(filters: str | dict | list | None = None):
	return _card(len(get_low_stock()))


def get_low_stock(limit=None):
	"""Items under their reorder level in that warehouse (Item > Auto re-order)."""
	if not frappe.has_permission("Bin"):
		return []
	rows = frappe.db.sql(
		"""
		select ir.parent as item_code, i.item_name, ir.warehouse, ir.warehouse_reorder_level as reorder_level,
			ifnull(b.actual_qty, 0) as actual_qty, i.stock_uom
		from `tabItem Reorder` ir
		join `tabItem` i on i.name = ir.parent and i.disabled = 0
		left join `tabBin` b on b.item_code = ir.parent and b.warehouse = ir.warehouse
		where ir.warehouse_reorder_level > 0 and ifnull(b.actual_qty, 0) < ir.warehouse_reorder_level
		order by ifnull(b.actual_qty, 0) / ir.warehouse_reorder_level, i.item_name
		""",
		as_dict=True,
	)
	return rows[:limit] if limit else rows


# ------------------------------------------------------------ board


@frappe.whitelist()
def get_board_data(branch: str | None = None):
	frappe.has_permission("Repair Order", throw=True)
	now = now_datetime()
	filters = _branch_filters(branch)
	orders = frappe.get_list(
		"Repair Order",
		filters={**filters, "status": ("in", OPEN_STATUSES)},
		fields=[
			"name",
			"status",
			"customer_name",
			"mobile_no",
			"gun",
			"gun_type",
			"technician",
			"expected_delivery",
			"grand_total",
			"balance",
			"branch",
		],
		order_by="expected_delivery asc",
		limit_page_length=500,
	)
	services = {}
	if orders:
		for row in frappe.get_all(
			"Repair Order Service",
			filters={"parent": ("in", [o.name for o in orders]), "parenttype": "Repair Order"},
			fields=["parent", "item_name", "service_item"],
			order_by="idx",
		):
			services.setdefault(row.parent, []).append(row.item_name or row.service_item)

	for order in orders:
		order.services = services.get(order.name, [])
		order.late = order.status in WORKING_STATUSES and get_datetime(order.expected_delivery) < now
		order.due_today = getdate(order.expected_delivery) == getdate(now)

	# SQL aggregates in get_list fields are refused on Frappe 16; a day's deliveries are few
	delivered_today = frappe.get_list(
		"Repair Order",
		filters={**filters, "status": "Delivered", "delivered_on": (">=", getdate(now))},
		pluck="grand_total",
		limit_page_length=0,
	)

	return {
		"orders": orders,
		"kpis": {
			"working": sum(1 for o in orders if o.status in WORKING_STATUSES),
			"ready": sum(1 for o in orders if o.status == "Ready for Delivery"),
			"late": sum(1 for o in orders if o.late),
			"due_today": sum(1 for o in orders if o.due_today and o.status in WORKING_STATUSES),
			"delivered_today": len(delivered_today),
			"delivered_today_amount": sum(flt(t) for t in delivered_today),
			"unpaid": sum(flt(o.balance) for o in orders),
		},
		"low_stock": get_low_stock(limit=8),
		"currency": frappe.db.get_default("currency"),
		"server_time": str(now),
	}


@frappe.whitelist()
def get_branches():
	settings = frappe.get_cached_doc("Workshop Settings")
	branches = [row.branch for row in settings.branches]
	return {"branches": branches, "default": settings.default_branch}
