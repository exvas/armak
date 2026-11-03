// Copyright (c) 2026, sammish and contributors
// For license information, please see license.txt

frappe.ui.form.on("Repair Order", {
	setup(frm) {
		frm.set_query("gun", () => ({
			filters: frm.doc.customer
				? { customer: frm.doc.customer, disabled: 0 }
				: { disabled: 0 },
		}));
		frm.set_query("technician", () => ({
			query: "frappe.core.doctype.user.user.user_query",
			filters: { ignore_user_type: 1 },
		}));
		frm.set_query("service_item", "services", () => ({
			filters: { is_sales_item: 1, disabled: 0, is_stock_item: 0 },
		}));
		frm.set_query("item_code", "materials", () => ({
			filters: { is_stock_item: 1, disabled: 0 },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.branch) {
			frappe.db.get_single_value("Workshop Settings", "default_branch").then((branch) => {
				if (branch) frm.set_value("branch", branch);
			});
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const status = frm.doc.status;
		const open = !["Delivered", "Cancelled"].includes(status);

		if (status === "Received") {
			frm.add_custom_button(__("Start Work"), () => start_work(frm));
		}
		if (["Received", "In Progress"].includes(status)) {
			frm.add_custom_button(__("Ready for Delivery"), () => mark_ready(frm)).addClass(
				"btn-primary"
			);
		}
		if (status === "Ready for Delivery") {
			frm.add_custom_button(__("Deliver & Invoice"), () => deliver(frm)).addClass(
				"btn-primary"
			);
		}
		if (open) {
			frm.add_custom_button(
				__("Receive Advance"),
				() => receive_advance(frm),
				__("Payment")
			);
		}
		frm.add_custom_button(
			__("Gun History"),
			() => frappe.set_route("List", "Repair Order", { gun: frm.doc.gun }),
			__("View")
		);
	},

	gun(frm) {
		if (!frm.doc.gun) return;
		frappe.db.get_value("Gun", frm.doc.gun, "customer").then(({ message }) => {
			if (message && message.customer && message.customer !== frm.doc.customer) {
				frm.set_value("customer", message.customer);
			}
		});
	},

	customer(frm) {
		if (!frm.doc.gun || !frm.doc.customer) return;
		frappe.db.get_value("Gun", frm.doc.gun, "customer").then(({ message }) => {
			if (message && message.customer !== frm.doc.customer) frm.set_value("gun", null);
		});
	},

	branch(frm) {
		if (!frm.doc.branch) return;
		frappe
			.call("armak.workshop.doctype.repair_order.repair_order.get_branch_company", {
				branch: frm.doc.branch,
			})
			.then(({ message }) => message && frm.set_value("company", message));
	},
});

frappe.ui.form.on("Repair Order Service", {
	service_item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.service_item) return;
		frappe
			.call("armak.workshop.doctype.repair_order.repair_order.get_service_rate", {
				item_code: row.service_item,
			})
			.then(({ message }) => frappe.model.set_value(cdt, cdn, "rate", message || 0));
	},
	qty: set_amount,
	rate: set_amount,
});

function set_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}

function call_doc(frm, method, args) {
	return frm.call({ doc: frm.doc, method, args, freeze: true }).then((r) => {
		frm.reload_doc();
		return r.message;
	});
}

function start_work(frm) {
	frappe.prompt(
		[
			{
				fieldname: "technician",
				fieldtype: "Link",
				options: "User",
				label: __("Technician"),
				default: frm.doc.technician || frappe.session.user,
			},
		],
		(v) => call_doc(frm, "start_work", v),
		__("Start Work"),
		__("Start")
	);
}

function mark_ready(frm) {
	const n = (frm.doc.materials || []).length;
	const msg = n
		? __("{0} material line(s) will be issued from stock. Check the quantities first.", [n])
		: __("No materials are listed, nothing will be issued from stock.");
	frappe.confirm(msg, () => call_doc(frm, "mark_ready"));
}

function payment_fields(amount_label, default_amount) {
	return [
		{
			fieldname: "mode_of_payment",
			fieldtype: "Link",
			options: "Mode of Payment",
			label: __("Mode of Payment"),
			default: "Cash",
		},
		{
			fieldname: "amount",
			fieldtype: "Currency",
			label: amount_label,
			default: default_amount,
		},
	];
}

function receive_advance(frm) {
	frappe.prompt(
		payment_fields(__("Advance Amount"), 0),
		(v) =>
			call_doc(frm, "receive_advance", {
				amount: v.amount,
				mode_of_payment: v.mode_of_payment,
			}).then((name) =>
				frappe.show_alert({
					message: __("Advance {0} recorded", [name]),
					indicator: "green",
				})
			),
		__("Receive Advance"),
		__("Record")
	);
}

function deliver(frm) {
	frappe.prompt(
		payment_fields(__("Balance Paid Now"), frm.doc.balance),
		(v) =>
			call_doc(frm, "deliver", {
				mode_of_payment: v.mode_of_payment,
				amount_paid: v.amount,
			}).then((invoice) =>
				frappe.show_alert({
					message: __("Invoice {0} created", [invoice]),
					indicator: "green",
				})
			),
		__("Deliver & Invoice"),
		__("Deliver")
	);
}
