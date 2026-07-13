package main

// MonthlyBudgetUSD is the reference monthly budget that metered spend is expressed
// as a percentage of in the /spend display fields.
const MonthlyBudgetUSD = 1100.0

// formatSpendDisplay renders a USD amount as "$X.YY (estimated A.AA% of $1100)",
// the percentage being the amount's share of the monthly budget. Both the dollar
// amount and the percentage are shown to 2 decimal places.
func formatSpendDisplay(usd float64) string {
	return "" // TODO(BILL-249): implement — Phase 0 stub, tests are RED against this
}
