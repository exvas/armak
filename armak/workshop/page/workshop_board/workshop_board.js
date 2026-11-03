// Copyright (c) 2026, sammish and contributors
// For license information, please see license.txt

const COLUMNS = [
	{ status: "Received", label: __("Received"), color: "var(--wb-received)" },
	{ status: "In Progress", label: __("In Progress"), color: "var(--wb-progress)" },
	{ status: "Ready for Delivery", label: __("Ready for Pickup"), color: "var(--wb-ready)" },
];
const REFRESH_MS = 60 * 1000;

frappe.pages["workshop-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Workshop Board"),
		single_column: true,
	});
	wrapper.workshop_board = new WorkshopBoard(page);
};

frappe.pages["workshop-board"].on_page_show = function (wrapper) {
	wrapper.workshop_board && wrapper.workshop_board.refresh();
};

class WorkshopBoard {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.search = "";
		this.focus = null; // kpi filter: late | today | null
		this.make();
		this.load_branches().then(() => this.refresh());
		// the page stays loaded after leaving it; only refresh while it is on screen
		const visible = () => frappe.get_route_str() === "workshop-board";
		this.timer = setInterval(() => visible() && this.refresh(), REFRESH_MS);
		frappe.realtime.doctype_subscribe("Repair Order");
		frappe.realtime.on("list_update", (msg) => {
			if (msg && msg.doctype === "Repair Order" && visible()) this.refresh_soon();
		});
	}

	make() {
		const page = this.page;
		page.set_primary_action(
			__("New Repair Order"),
			() => frappe.new_doc("Repair Order"),
			"add"
		);
		page.add_inner_button(__("Refresh"), () => this.refresh());
		page.add_inner_button(__("Full Screen"), () => this.toggle_fullscreen());

		this.$root = $(`
			<div class="wb">
				<div class="wb-toolbar">
					<div class="wb-search"></div>
					<div class="wb-branch"></div>
					<span class="wb-updated"></span>
				</div>
				<div class="wb-kpis"></div>
				<div class="wb-main">
					<div class="wb-board"></div>
					<aside class="wb-side"></aside>
				</div>
			</div>
		`).appendTo(page.body);

		this.search_field = frappe.ui.form.make_control({
			parent: this.$root.find(".wb-search"),
			df: {
				fieldtype: "Data",
				fieldname: "search",
				placeholder: __("Search gun no, customer, mobile or order"),
			},
			render_input: true,
		});
		this.search_field.$input.on(
			"input",
			frappe.utils.debounce(() => {
				this.search = (this.search_field.get_value() || "").trim().toLowerCase();
				this.render_board();
			}, 150)
		);

		this.branch_field = frappe.ui.form.make_control({
			parent: this.$root.find(".wb-branch"),
			df: {
				fieldtype: "Link",
				fieldname: "branch",
				options: "Branch",
				placeholder: __("All branches"),
				change: () => this.refresh(),
			},
			render_input: true,
		});

		this.$root.on("click", ".wb-kpi[data-focus]", (e) => {
			const focus = $(e.currentTarget).attr("data-focus");
			this.focus = this.focus === focus ? null : focus;
			this.render_kpis();
			this.render_board();
		});
		this.$root.on("click", ".wb-kpi[data-route]", (e) => {
			frappe.set_route($(e.currentTarget).attr("data-route").split("/"));
		});
		this.$root.on("click", ".wb-card", (e) => {
			if ($(e.target).closest("a").length) return;
			frappe.set_route("Form", "Repair Order", $(e.currentTarget).attr("data-name"));
		});
	}

	load_branches() {
		return frappe
			.xcall("armak.workshop.dashboard.get_branches")
			.then((r) => {
				const saved = this.saved_branch();
				const branch = saved !== null ? saved : r.default || "";
				this.branch_field.set_value(branch);
			})
			.catch(() => null);
	}

	saved_branch() {
		try {
			return localStorage.getItem("armak_wb_branch");
		} catch (e) {
			return null;
		}
	}

	refresh_soon() {
		clearTimeout(this.soon);
		this.soon = setTimeout(() => this.refresh(), 800);
	}

	refresh() {
		const branch = this.branch_field.get_value() || "";
		try {
			localStorage.setItem("armak_wb_branch", branch);
		} catch (e) {
			// private mode: the branch is simply not remembered
		}
		return frappe
			.xcall("armak.workshop.dashboard.get_board_data", { branch: branch || null })
			.then((data) => {
				this.data = data;
				// due times are in the site time zone; measure them against the server clock,
				// not the browser's, or every card is off by the time zone difference
				this.clock_offset = frappe.datetime.str_to_obj(data.server_time) - new Date();
				this.render();
			});
	}

	toggle_fullscreen() {
		$("body").toggleClass("wb-fullscreen");
		if ($("body").hasClass("wb-fullscreen")) {
			frappe.show_alert({
				message: __("Press Esc to leave full screen"),
				indicator: "blue",
			});
			$(document).one(
				"keyup.wb",
				(e) => e.key === "Escape" && $("body").removeClass("wb-fullscreen")
			);
		}
	}

	render() {
		this.$root
			.find(".wb-updated")
			.text(
				__("Updated {0}", [
					frappe.datetime.str_to_user(this.data.server_time).split(" ")[1] || "",
				])
			);
		this.render_kpis();
		this.render_board();
		this.render_side();
	}

	money(value) {
		return format_currency(value || 0, this.data.currency, 3);
	}

	render_kpis() {
		const k = this.data.kpis;
		const tile = ({ label, value, sub, dot, focus, route, alert }) => `
			<button class="wb-kpi ${this.focus && this.focus === focus ? "active" : ""} ${
			alert ? "is-alert" : ""
		}"
				${focus ? `data-focus="${focus}"` : ""} ${route ? `data-route="${route}"` : ""}>
				<div class="wb-kpi-label"><span class="wb-kpi-dot" style="--dot:${dot}"></span>${label}</div>
				<div class="wb-kpi-value">${value}</div>
				<div class="wb-kpi-sub">${sub || "&nbsp;"}</div>
			</button>`;
		this.$root.find(".wb-kpis").html(
			[
				tile({
					label: __("In Workshop"),
					value: k.working,
					sub: __("received or in progress"),
					dot: "var(--wb-progress)",
				}),
				tile({
					label: __("Due Today"),
					value: k.due_today,
					sub: __("tap to show"),
					dot: "var(--wb-progress)",
					focus: "today",
				}),
				tile({
					label: __("Late"),
					value: k.late,
					sub: k.late ? __("past delivery time") : __("all on time"),
					dot: "var(--wb-late)",
					focus: "late",
					alert: k.late > 0,
				}),
				tile({
					label: __("Ready for Pickup"),
					value: k.ready,
					sub: __("call the customer"),
					dot: "var(--wb-ready)",
				}),
				tile({
					label: __("Delivered Today"),
					value: k.delivered_today,
					sub: this.money(k.delivered_today_amount),
					dot: "var(--wb-ok)",
					route: "List/Repair Order",
				}),
				tile({
					label: __("To Collect"),
					value: this.money(k.unpaid),
					sub: __("balance on open orders"),
					dot: "var(--gray-500)",
				}),
			].join("")
		);
	}

	matches(order) {
		if (this.focus === "late" && !order.late) return false;
		if (this.focus === "today" && !order.due_today) return false;
		if (!this.search) return true;
		return [order.name, order.gun, order.customer_name, order.mobile_no, order.gun_type]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(this.search));
	}

	render_board() {
		const orders = this.data.orders.filter((o) => this.matches(o));
		const html = COLUMNS.map((col) => {
			const rows = orders.filter((o) => o.status === col.status);
			const cards = rows.length
				? rows.map((o) => this.card(o, col)).join("")
				: `<div class="wb-empty">${
						this.search || this.focus ? __("No matching orders") : __("Nothing here")
				  }</div>`;
			return `
				<section class="wb-col">
					<div class="wb-col-head">
						<span class="wb-kpi-dot" style="--dot:${col.color}"></span>${col.label}
						<span class="wb-count">${rows.length}</span>
					</div>
					${cards}
				</section>`;
		}).join("");
		this.$root.find(".wb-board").html(html);
	}

	due_text(order) {
		const due = frappe.datetime.str_to_obj(order.expected_delivery);
		const now = new Date(Date.now() + (this.clock_offset || 0));
		const mins = Math.round((due - now) / 60000);
		const abs = Math.abs(mins);
		const span =
			abs < 60
				? __("{0} min", [abs])
				: abs < 1440
				? __("{0} h", [Math.round(abs / 60)])
				: __("{0} d", [Math.round(abs / 1440)]);
		if (order.status === "Ready for Delivery") return { text: __("Ready"), cls: "" };
		if (mins < 0) return { text: __("{0} late", [span]), cls: "is-late" };
		if (order.due_today) return { text: __("due in {0}", [span]), cls: "is-today" };
		return {
			text: frappe.datetime.str_to_user(order.expected_delivery).split(" ")[0],
			cls: "",
		};
	}

	card(order, col) {
		const esc = frappe.utils.escape_html;
		const due = this.due_text(order);
		const chips = (order.services || [])
			.map((s) => `<span class="wb-chip">${esc(s)}</span>`)
			.join("");
		const tech = order.technician ? frappe.avatar(order.technician, "avatar-xs") : "";
		const phone = order.mobile_no
			? `<a href="tel:${esc(order.mobile_no)}">${esc(order.mobile_no)}</a>`
			: "";
		return `
			<div class="wb-card ${order.late ? "is-late" : ""}" style="--accent:${col.color}" data-name="${esc(
			order.name
		)}">
				<div class="wb-card-top">
					<span class="wb-gun">${esc(order.gun)}</span>
					<span class="wb-order">${esc(order.name)}</span>
				</div>
				<div class="wb-customer"><span>${esc(order.customer_name || "")}</span>${phone}</div>
				<div class="wb-services">${chips}</div>
				<div class="wb-card-foot">
					<span class="wb-due ${due.cls}">${due.text}</span>
					<span class="wb-balance ${order.balance > 0 ? "is-due" : ""}">${
			order.balance > 0 ? __("Due {0}", [this.money(order.balance)]) : __("Paid")
		}</span>
					${tech}
				</div>
			</div>`;
	}

	render_side() {
		const esc = frappe.utils.escape_html;
		const low = this.data.low_stock || [];
		const stock = low.length
			? low
					.map((r) => {
						const pct = Math.max(
							0,
							Math.min(100, (r.actual_qty / r.reorder_level) * 100)
						);
						return `
						<div class="wb-stock-row">
							<div class="wb-stock-name">
								<span>${esc(r.item_name || r.item_code)}</span>
								<span class="wb-stock-qty">${format_number(r.actual_qty, null, 2)} / ${format_number(
							r.reorder_level,
							null,
							2
						)} ${esc(r.stock_uom || "")}</span>
							</div>
							<div class="wb-bar"><span style="width:${pct}%"></span></div>
						</div>`;
					})
					.join("")
			: `<div class="wb-empty">${__("All materials above their minimum level")}</div>`;
		this.$root.find(".wb-side").html(`
			<div class="wb-panel">
				<h4>${__(
					"Low Stock"
				)}<a class="text-muted small" href="/app/query-report/Stock Projected Qty">${__(
			"All"
		)}</a></h4>
				${stock}
			</div>
			<div class="wb-panel wb-links">
				<h4>${__("Quick Links")}</h4>
				<a href="/app/gun/new">${__("Register a Gun")}</a>
				<a href="/app/repair-order?status=Ready%20for%20Delivery">${__("Ready for Pickup list")}</a>
				<a href="/app/query-report/Repair Order Profit">${__("Profit per Job")}</a>
				<a href="/app/query-report/Workshop Material Consumption">${__("Material Consumption")}</a>
				<a href="/app/workshop">${__("Workshop Dashboard")}</a>
			</div>`);
	}
}
