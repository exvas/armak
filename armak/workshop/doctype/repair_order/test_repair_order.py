# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime

COMPANY = "Wind Power LLC"
BRANCH = "_Test Workshop Branch"
WAREHOUSE = "Stores - WP"
SERVICE = "_Test Black Painting"
PAINT = "_Test Black Paint"


def make_item(item_code, is_stock_item, rate=0):
	if not frappe.db.exists("Item", item_code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_group": "Services" if not is_stock_item else "Raw Material",
				"stock_uom": "Kg" if is_stock_item else "Nos",
				"is_stock_item": is_stock_item,
				"valuation_rate": 4 if is_stock_item else 0,
			}
		).insert()
	if rate:
		price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": item_code,
					"price_list": price_list,
					"price_list_rate": rate,
				}
			).insert()


class TestRepairOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Branch", BRANCH):
			frappe.get_doc({"doctype": "Branch", "branch": BRANCH}).insert()
		settings = frappe.get_doc("Workshop Settings")
		settings.set(
			"branches",
			[
				{
					"branch": BRANCH,
					"company": COMPANY,
					"materials_warehouse": WAREHOUSE,
					"cost_center": "Main - WP",
				}
			],
		)
		settings.default_branch = BRANCH
		settings.save()

		cash = frappe.get_doc("Mode of Payment", "Cash")
		if not any(a.company == COMPANY for a in cash.accounts):
			cash.append("accounts", {"company": COMPANY, "default_account": "Cash - WP"})
			cash.save()

		make_item(SERVICE, 0, rate=20)
		make_item(PAINT, 1)
		if not frappe.db.exists("Service Material Template", SERVICE):
			frappe.get_doc(
				{
					"doctype": "Service Material Template",
					"service_item": SERVICE,
					"items": [{"item_code": PAINT, "qty": 0.25}],
				}
			).insert()
		make_stock_entry(item_code=PAINT, target=WAREHOUSE, qty=10, basic_rate=4, company=COMPANY)

		if not frappe.db.exists("Customer", {"armak_civil_id": "_T-12345"}):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test Gun Owner",
					"armak_civil_id": "_T-12345",
					"customer_group": "Individual",
					"territory": "All Territories",
				}
			).insert()
		cls.customer = frappe.db.get_value("Customer", {"armak_civil_id": "_T-12345"})
		if not frappe.db.exists("Gun", "_T-GUN-1"):
			frappe.get_doc(
				{"doctype": "Gun", "gun_number": "_t-gun-1", "customer": cls.customer, "gun_type": "Rifle"}
			).insert()

	def make_order(self, qty=1):
		return frappe.get_doc(
			{
				"doctype": "Repair Order",
				"company": COMPANY,
				"branch": BRANCH,
				"gun": "_T-GUN-1",
				"expected_delivery": add_days(now_datetime(), 2),
				"services": [{"service_item": SERVICE, "qty": qty, "description": "Full black paint"}],
			}
		).insert()

	def test_gun_number_is_normalised(self):
		# MariaDB compares names case-insensitively, so check the stored spelling itself
		self.assertEqual(frappe.db.get_value("Gun", {"gun_number": "_t-gun-1"}, "name"), "_T-GUN-1")

	def test_draft_fills_customer_rate_and_template_materials(self):
		order = self.make_order(qty=4)
		self.assertEqual(order.customer, self.customer)
		self.assertEqual(order.customer_name, "_Test Gun Owner")
		self.assertEqual(order.civil_id, "_T-12345")
		self.assertEqual(order.status, "Draft")
		self.assertEqual(flt(order.total), 80)
		self.assertEqual(len(order.materials), 1)
		self.assertEqual(flt(order.materials[0].qty), 1.0)  # 0.25 kg per gun x 4

	def test_full_flow(self):
		order = self.make_order()
		order.submit()
		self.assertEqual(order.status, "Received")

		order.receive_advance(5, "Cash")
		order.reload()
		self.assertEqual(flt(order.advance_paid), 5)
		self.assertEqual(flt(order.balance), flt(order.grand_total) - 5)

		order.start_work()
		self.assertEqual(order.status, "In Progress")

		order.mark_ready()
		order.reload()
		self.assertEqual(order.status, "Ready for Delivery")
		se = frappe.get_doc("Stock Entry", order.stock_entry)
		self.assertEqual(se.docstatus, 1)
		self.assertEqual(se.armak_repair_order, order.name)
		self.assertEqual(flt(order.material_cost), 1.0)  # 0.25 kg x 4

		with self.assertRaises(frappe.ValidationError):
			order.materials[0].qty = 2
			order.save()
		order.reload()

		order.deliver("Cash", order.balance)
		order.reload()
		self.assertEqual(order.status, "Delivered")
		si = frappe.get_doc("Sales Invoice", order.sales_invoice)
		self.assertEqual(si.docstatus, 1)
		self.assertEqual(flt(si.outstanding_amount), 0)
		self.assertEqual(flt(si.total_advance), 5)
		self.assertEqual(flt(order.balance), 0)
		self.assertEqual(flt(order.advance_paid), 5)
		self.assertEqual(flt(order.profit), 19)
		if si.meta.has_field("branch"):  # with the Branch accounting dimension
			self.assertEqual(si.branch, BRANCH)

		with self.assertRaises(frappe.ValidationError):
			order.mark_ready()

	def test_cancel_returns_materials(self):
		order = self.make_order()
		order.submit()
		order.mark_ready()
		order.reload()
		order.cancel()
		self.assertEqual(frappe.db.get_value("Stock Entry", order.stock_entry, "docstatus"), 2)
		self.assertEqual(order.status, "Cancelled")

	def test_print_formats_render(self):
		order = self.make_order()
		bilingual = frappe.get_print(
			"Repair Order", order.name, print_format="Repair Order Bilingual", doc=order
		)
		self.assertIn("أمر إصلاح", bilingual)
		self.assertIn("_T-GUN-1", bilingual)
		tag = frappe.get_print("Repair Order", order.name, print_format="Repair Order Gun Tag", doc=order)
		self.assertIn("data:image/png;base64,", tag)
		self.assertIn(order.name, tag)

	def test_dashboard_and_reports(self):
		from frappe.utils import nowdate

		from armak.workshop import dashboard
		from armak.workshop.dashboard_chart_source.workshop_revenue_by_service import (
			workshop_revenue_by_service as by_service,
		)
		from armak.workshop.report.repair_order_profit import repair_order_profit
		from armak.workshop.report.workshop_material_consumption import workshop_material_consumption

		late = self.make_order()
		late.expected_delivery = add_days(now_datetime(), -1)
		late.submit()
		delivered = self.make_order()
		delivered.submit()
		delivered.receive_advance(5, "Cash")
		delivered.mark_ready()
		delivered.reload()
		delivered.deliver("Cash", delivered.balance)

		self.assertGreaterEqual(dashboard.late_orders()["value"], 1)
		self.assertGreaterEqual(dashboard.open_orders()["value"], 1)
		self.assertGreaterEqual(dashboard.todays_collections()["value"], flt(delivered.grand_total))

		board = dashboard.get_board_data(BRANCH)
		row = next(o for o in board["orders"] if o.name == late.name)
		self.assertTrue(row.late)
		self.assertEqual(row.services, [SERVICE])
		self.assertNotIn(delivered.name, [o.name for o in board["orders"]])
		self.assertGreaterEqual(board["kpis"]["delivered_today"], 1)

		chart = by_service.get(filters={"branch": BRANCH, "period": "This Month"}, no_cache=1)
		self.assertIn(SERVICE, chart["labels"])

		filters = {"company": COMPANY, "branch": BRANCH, "from_date": nowdate(), "to_date": nowdate()}
		_cols, rows, _msg, _chart, summary = repair_order_profit.execute(filters)
		row = next(r for r in rows if r.name == delivered.name)
		self.assertEqual(flt(row.profit), 19)
		self.assertEqual(round(row.margin), 95)
		self.assertTrue(summary)

		_cols, rows, _msg, _chart = workshop_material_consumption.execute(filters)
		paint = next(r for r in rows if r.item_code == PAINT)
		self.assertGreaterEqual(flt(paint.qty), 0.25)
		self.assertGreaterEqual(paint.orders, 1)

		frappe.get_doc(
			{
				"doctype": "Item Reorder",
				"parent": PAINT,
				"parenttype": "Item",
				"parentfield": "reorder_levels",
				"warehouse": WAREHOUSE,
				"warehouse_reorder_level": 1000,
				"warehouse_reorder_qty": 10,
				"material_request_type": "Purchase",
			}
		).db_insert()
		self.assertIn(PAINT, [r.item_code for r in dashboard.get_low_stock()])
