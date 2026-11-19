# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

from urllib.parse import quote

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime

COMPANY = "Wind Power LLC"
BRANCH = "_Test Workshop Branch"
WAREHOUSE = "Stores - WP"
SERVICE = "_Test Black Painting"
PAINT = "_Test Black Paint"
FINISHED = "Finished Goods - WP"
COVER = "_Test Rifle Cover"
FABRIC = "_Test Cover Fabric"
ZIPPER = "_Test Cover Zipper"
COUNTER_USER = "_test_workshop_counter@example.com"
OWNER_MOBILE = "+968 9100 0001"
TAILOR_USER = "_test_workshop_tailor@example.com"


def make_user(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
	return email


def make_cover_bom():
	"""One 60 m fabric roll and 10 zippers make 10 covers (the client's example)."""
	for item_code, is_stock_item in ((COVER, 1), (FABRIC, 1), (ZIPPER, 1)):
		make_item(item_code, is_stock_item)
	bom = frappe.db.get_value("BOM", {"item": COVER, "is_default": 1, "docstatus": 1})
	if not bom:
		doc = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": COVER,
				"company": COMPANY,
				"quantity": 10,
				"rm_cost_as_per": "Valuation Rate",
				"items": [
					{"item_code": FABRIC, "qty": 60, "rate": 2},
					{"item_code": ZIPPER, "qty": 10, "rate": 0.5},
				],
			}
		).insert()
		doc.submit()
		bom = doc.name
	make_stock_entry(item_code=FABRIC, target=WAREHOUSE, qty=100, basic_rate=2, company=COMPANY)
	make_stock_entry(item_code=ZIPPER, target=WAREHOUSE, qty=50, basic_rate=0.5, company=COMPANY)
	return bom


def selling_price_list():
	"""A selling price list in the company currency (ERPNext's v16 test data makes its lists INR)."""
	from armak.workshop.doctype.repair_order.repair_order import get_price_list

	price_list = get_price_list(COMPANY)
	if not price_list:
		price_list = (
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": "_Test Workshop Selling",
					"currency": frappe.db.get_value("Company", COMPANY, "default_currency"),
					"selling": 1,
					"enabled": 1,
				}
			)
			.insert()
			.name
		)
	return price_list


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
		price_list = selling_price_list()
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
					"production_warehouse": WAREHOUSE,
					"finished_goods_warehouse": FINISHED,
					"cost_center": "Main - WP",
				}
			],
		)
		settings.default_branch = BRANCH
		settings.prices_include_vat = 1  # the client's answer: VAT is inside the price
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
					"mobile_no": OWNER_MOBILE,
					"customer_group": "Individual",
					"territory": "All Territories",
				}
			).insert()
		cls.customer = frappe.db.get_value("Customer", {"armak_civil_id": "_T-12345"})
		frappe.db.set_value("Customer", cls.customer, "mobile_no", OWNER_MOBILE)
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
		# 4 x 20, VAT included: the customer pays 80 and the VAT inside it is worked out
		rate = order.vat_rate()
		self.assertEqual(flt(order.grand_total), 80)
		self.assertEqual(flt(order.tax_amount), flt(80 * rate / (100 + rate), order.precision("tax_amount")))
		self.assertEqual(flt(order.total + order.tax_amount, order.precision("total")), 80)
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
		self.assertEqual(si.currency, frappe.db.get_value("Company", COMPANY, "default_currency"))
		self.assertEqual(flt(si.items[0].rate), 20)
		self.assertEqual(flt(si.rounded_total or si.grand_total), 20)  # VAT inside the 20
		self.assertEqual(flt(si.outstanding_amount), 0)
		self.assertEqual(flt(si.total_advance), 5)
		self.assertEqual(flt(order.balance), 0)
		self.assertEqual(flt(order.advance_paid), 5)
		self.assertEqual(flt(order.profit), flt(si.base_net_total) - 1)  # net of VAT less 1 of paint
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
		net = frappe.db.get_value("Sales Invoice", delivered.sales_invoice, "base_net_total")
		self.assertEqual(flt(row.profit), flt(net) - 1)
		self.assertEqual(round(row.margin), round((flt(net) - 1) / flt(row.revenue) * 100))
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

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_production_entry_as_tailor(self):
		bom = make_cover_bom()
		frappe.set_user(make_user(TAILOR_USER, "Workshop Tailor"))
		entry = frappe.get_doc(
			{
				"doctype": "Production Entry",
				"company": COMPANY,
				"branch": BRANCH,
				"item_code": COVER,
				"qty": 6,
			}
		)
		entry.insert()
		self.assertEqual(entry.bom, bom)
		self.assertEqual(entry.source_warehouse, WAREHOUSE)
		self.assertEqual(entry.target_warehouse, FINISHED)
		materials = {row.item_code: row for row in entry.materials}
		self.assertEqual(flt(materials[FABRIC].qty), 36)  # 60 m per 10 covers, 6 made
		self.assertEqual(flt(materials[ZIPPER].qty), 6)

		materials[FABRIC].qty = 38  # the tailor used a little more than the template
		entry.save()
		entry.submit()

		frappe.set_user("Administrator")
		entry.reload()
		se = frappe.get_doc("Stock Entry", entry.stock_entry)
		self.assertEqual(
			(se.purpose, se.docstatus, se.armak_production_entry), ("Manufacture", 1, entry.name)
		)
		self.assertEqual(se.owner, TAILOR_USER)
		finished = [d for d in se.items if d.is_finished_item]
		self.assertEqual([(d.item_code, flt(d.qty), d.t_warehouse) for d in finished], [(COVER, 6, FINISHED)])
		used = {d.item_code: flt(d.qty) for d in se.items if not d.is_finished_item}
		self.assertEqual(used, {FABRIC: 38, ZIPPER: 6})
		self.assertEqual(flt(entry.material_cost), 79)  # 38 x 2 + 6 x 0.5
		self.assertAlmostEqual(flt(entry.unit_cost), 79 / 6, places=3)

		from armak.workshop.report.workshop_production import workshop_production

		_cols, rows, _msg, _chart = workshop_production.execute(
			{
				"company": COMPANY,
				"item_code": COVER,
				"from_date": entry.posting_date,
				"to_date": entry.posting_date,
			}
		)
		self.assertGreaterEqual(sum(r.qty for r in rows), 6)

		entry.cancel()
		self.assertEqual(frappe.db.get_value("Stock Entry", entry.stock_entry, "docstatus"), 2)

	def test_counter_staff_full_flow(self):
		"""Counter staff hold only the Workshop Counter role, not Administrator's."""
		from armak.workshop import dashboard

		frappe.set_user(make_user(COUNTER_USER, "Workshop Counter"))
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Walk-in Hunter",
				"customer_group": "Individual",
				"territory": "All Territories",
				"mobile_no": "96812345678",
			}
		).insert()
		gun = frappe.get_doc(
			{"doctype": "Gun", "gun_number": "_T-GUN-COUNTER", "customer": customer.name}
		).insert()
		order = frappe.get_doc(
			{
				"doctype": "Repair Order",
				"company": COMPANY,
				"branch": BRANCH,
				"gun": gun.name,
				"expected_delivery": add_days(now_datetime(), 1),
				"services": [{"service_item": SERVICE, "qty": 1}],
			}
		).insert()
		order.submit()
		order.receive_advance(5, "Cash")
		order.reload()
		order.start_work()
		order.mark_ready()
		order.reload()
		order.deliver("Cash", order.balance)
		order.reload()
		self.assertEqual(order.status, "Delivered")
		self.assertEqual(frappe.db.get_value("Sales Invoice", order.sales_invoice, "outstanding_amount"), 0)
		self.assertTrue(frappe.has_permission("Sales Invoice", "print", order.sales_invoice))
		# booked by the system, but the audit trail names the counter user
		self.assertEqual(frappe.db.get_value("Sales Invoice", order.sales_invoice, "owner"), COUNTER_USER)
		self.assertEqual(frappe.db.get_value("Stock Entry", order.stock_entry, "owner"), COUNTER_USER)
		self.assertGreaterEqual(dashboard.todays_collections()["value"], flt(order.grand_total))
		self.assertTrue(dashboard.get_board_data(BRANCH)["kpis"])

	def test_prices_with_vat_on_top(self):
		frappe.db.set_single_value("Workshop Settings", "prices_include_vat", 0)
		try:
			order = self.make_order()
		finally:
			frappe.db.set_single_value("Workshop Settings", "prices_include_vat", 1)
		rate = order.vat_rate()
		self.assertFalse(order.prices_include_vat)
		self.assertEqual(flt(order.total), 20)
		self.assertEqual(flt(order.grand_total), flt(20 + 20 * rate / 100, order.precision("grand_total")))

	def test_register_by_mobile(self):
		from armak.workshop import registration

		frappe.set_user(make_user(COUNTER_USER, "Workshop Counter"))
		first = registration.register(
			mobile="9555 1234",
			customer_name="_Test Mobile Owner",
			gun_number="_t-gun-mob 1",
			gun_type="Shotgun",
		)
		self.assertEqual(first["gun"], "_T-GUN-MOB 1")
		self.assertEqual(frappe.db.get_value("Gun", first["gun"], "customer"), first["customer"])

		# the same mobile, written another way, finds the same customer; no name needed
		again = registration.register(mobile="+968 95551234", gun_number="_T-GUN-MOB 2", civil_id="_T-CIV-9")
		self.assertEqual(again["customer"], first["customer"])
		self.assertEqual(frappe.db.get_value("Customer", first["customer"], "armak_civil_id"), "_T-CIV-9")
		found = registration.lookup(gun_number="_t-gun-mob 2")
		self.assertEqual(found.name, first["customer"])
		self.assertEqual({g.name for g in found.guns}, {"_T-GUN-MOB 1", "_T-GUN-MOB 2"})

		# a gun belongs to one customer
		with self.assertRaises(frappe.ValidationError):
			registration.register(mobile="9555 9999", customer_name="_Test Other", gun_number="_T-GUN-MOB 1")
		# a new customer needs a name
		with self.assertRaises(frappe.ValidationError):
			registration.register(mobile="9555 8888")

	def test_mobile_is_required(self):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test No Mobile",
				"customer_group": "Individual",
				"territory": "All Territories",
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Gun", "gun_number": "_T-GUN-NOMOB", "customer": customer.name}
			).insert()

	def test_notify_customer_on_whatsapp(self):
		order = self.make_order()
		order.submit()
		with self.assertRaises(frappe.ValidationError):
			order.notify_customer("WhatsApp")  # not ready yet
		order.mark_ready()
		order.reload()
		link = order.notify_customer("WhatsApp")
		self.assertTrue(link.startswith("https://wa.me/96891000001?text="))
		self.assertIn(quote(order.name), link)
		order.reload()
		self.assertEqual(order.notified_via, "WhatsApp")
		self.assertTrue(order.customer_notified_on)
		self.assertEqual(order.notify_customer("Phone"), "tel:+96891000001")

	def test_gun_card_print(self):
		html = frappe.get_print("Gun", "_T-GUN-1", print_format="Gun Card")
		for text in ("_Test Gun Owner", OWNER_MOBILE, "_T-12345", "_T-GUN-1", "data:image/png;base64,"):
			self.assertIn(text, html)
