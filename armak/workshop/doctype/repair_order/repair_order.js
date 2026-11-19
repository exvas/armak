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
		// a new order starts from the customer's mobile (their Customer ID) or the gun number
		if (frm.is_new() && !frm.doc.customer && !frm.doc.gun) find_or_register(frm);
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Find / Register Customer"), () => find_or_register(frm));
		}
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
			frm.add_custom_button(
				__("WhatsApp"),
				() => notify(frm, "WhatsApp"),
				__("Notify Customer")
			);
			frm.add_custom_button(
				__("Phone Call"),
				() => notify(frm, "Phone"),
				__("Notify Customer")
			);
			if (frm.doc.customer_notified_on) {
				frm.dashboard.add_comment(
					__("Customer notified by {0} on {1}", [
						frm.doc.notified_via,
						frappe.datetime.str_to_user(frm.doc.customer_notified_on),
					]),
					"green",
					true
				);
			}
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
				company: frm.doc.company,
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

const REG = "armak.workshop.registration.";

function find_or_register(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Find or Register Customer"),
		fields: [
			{
				fieldname: "mobile",
				fieldtype: "Data",
				options: "Phone",
				label: __("Mobile (Customer ID)"),
				reqd: 1,
				change: () => look_up({ mobile: d.get_value("mobile") }),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "gun_number",
				fieldtype: "Data",
				label: __("Gun Number"),
				change: () =>
					!d.get_value("customer") && look_up({ gun_number: d.get_value("gun_number") }),
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "found", fieldtype: "HTML" },
			{ fieldname: "customer", fieldtype: "Data", hidden: 1 },
			{ fieldname: "customer_name", fieldtype: "Data", label: __("Customer Name") },
			{ fieldname: "civil_id", fieldtype: "Data", label: __("Civil ID (optional)") },
			{ fieldtype: "Column Break" },
			{ fieldname: "licence_no", fieldtype: "Data", label: __("Licence No (optional)") },
			{ fieldname: "gun_type", fieldtype: "Data", label: __("Gun Type (optional)") },
			{ fieldname: "make", fieldtype: "Data", label: __("Make (optional)") },
		],
		primary_action_label: __("Use"),
		primary_action(values) {
			frappe
				.call(REG + "register", {
					mobile: values.mobile,
					customer_name: values.customer_name,
					gun_number: values.gun_number,
					civil_id: values.civil_id,
					licence_no: values.licence_no,
					gun_type: values.gun_type,
					make: values.make,
				})
				.then(({ message }) => {
					d.hide();
					frm.set_value("customer", message.customer).then(() => {
						if (message.gun) frm.set_value("gun", message.gun);
					});
				});
		},
	});

	function look_up(args) {
		if (!Object.values(args).some(Boolean)) return;
		frappe.call(REG + "lookup", args).then(({ message }) => {
			const c = message || {};
			d.set_value("customer", c.name || "");
			const esc = frappe.utils.escape_html;
			if (!c.name) {
				d.get_field("found").$wrapper.html(
					`<p class="text-muted">${__(
						"New customer: enter the name to register them."
					)}</p>`
				);
				d.set_df_property("customer_name", "reqd", 1);
				return;
			}
			d.set_df_property("customer_name", "reqd", 0);
			d.set_value("customer_name", c.customer_name);
			if (args.gun_number) d.set_value("mobile", c.mobile_no);
			const guns = (c.guns || [])
				.map(
					(g) =>
						`<a class="btn btn-xs btn-default armak-pick-gun" data-gun="${esc(
							g.name
						)}">${esc(g.name)}${g.gun_type ? " · " + esc(g.gun_type) : ""}</a>`
				)
				.join(" ");
			d.get_field("found").$wrapper.html(`
				<p><b>${esc(c.customer_name)}</b> · ${esc(c.mobile_no || "")}${
				c.armak_civil_id ? " · " + __("Civil ID") + " " + esc(c.armak_civil_id) : ""
			}</p>
				<p>${guns || `<span class="text-muted">${__("No guns registered yet")}</span>`}</p>`);
			d.get_field("found")
				.$wrapper.find(".armak-pick-gun")
				.on("click", (e) => {
					d.set_value("gun_number", $(e.currentTarget).attr("data-gun"));
				});
		});
	}

	d.show();
	d.get_field("mobile").$input.focus();
}

function notify(frm, channel) {
	if (!frm.doc.mobile_no) {
		frappe.msgprint(__("The customer has no mobile number."));
		return;
	}
	frm.call({ doc: frm.doc, method: "notify_customer", args: { channel } }).then(
		({ message }) => {
			if (message) window.open(message, channel === "WhatsApp" ? "_blank" : "_self");
			frm.reload_doc();
		}
	);
}
