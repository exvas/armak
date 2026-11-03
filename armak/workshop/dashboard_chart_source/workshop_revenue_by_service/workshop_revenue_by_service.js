frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Workshop Revenue by Service"] = {
	method: "armak.workshop.dashboard_chart_source.workshop_revenue_by_service.workshop_revenue_by_service.get",
	filters: [
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["This Month", "Last 3 Months", "This Year"],
			default: "This Month",
		},
	],
};
