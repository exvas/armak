// Copyright (c) 2026, sammish and contributors
// For license information, please see license.txt

const PE_METHOD = "armak.workshop.doctype.production_entry.production_entry.";

frappe.ui.form.on("Production Entry", {
	setup(frm) {
		frm.set_query("item_code", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
		frm.set_query("bom", () => ({
			filters: { item: frm.doc.item_code, is_active: 1, docstatus: 1 },
		}));
		frm.set_query("item_code", "materials", () => ({
			filters: { is_stock_item: 1, disabled: 0 },
		}));
		for (const field of ["source_warehouse", "target_warehouse"]) {
			frm.set_query(field, () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		}
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.branch) {
			frappe.db.get_single_value("Workshop Settings", "default_branch").then((branch) => {
				if (branch) frm.set_value("branch", branch);
			});
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () =>
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry)
			);
		}
	},

	branch(frm) {
		if (!frm.doc.branch) return;
		frappe
			.call(PE_METHOD + "get_branch_defaults", { branch: frm.doc.branch })
			.then(({ message }) => {
				// the branch's warehouses, keeping any the user already chose
				for (const [field, value] of Object.entries(message || {})) {
					if (value && (field === "company" || !frm.doc[field]))
						frm.set_value(field, value);
				}
			});
	},

	item_code(frm) {
		if (!frm.doc.item_code) return;
		frappe
			.call(PE_METHOD + "get_product_bom", { item_code: frm.doc.item_code })
			.then(({ message }) => {
				if (!message) {
					frappe.msgprint(
						__("{0} has no material template yet. Create a Bill of Materials first.", [
							frm.doc.item_code,
						])
					);
				}
				frm.set_value("bom", message || null);
			});
	},

	bom: refill_materials,
	qty: refill_materials,
});

function refill_materials(frm) {
	if (!frm.doc.bom || !flt(frm.doc.qty)) return;
	frappe
		.call(PE_METHOD + "get_bom_materials", { bom: frm.doc.bom, qty: frm.doc.qty })
		.then(({ message }) => {
			frm.clear_table("materials");
			(message || []).forEach((row) => frm.add_child("materials", row));
			frm.refresh_field("materials");
		});
}
