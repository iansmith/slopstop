package main

import "fmt"

// MonthlyBudgetUSD is the reference monthly budget that metered spend is expressed
// as a percentage of in the /spend display fields. It is the single source of the
// budget figure — every spend estimate reads it here, not a bare literal.
const MonthlyBudgetUSD = 1100.0

// formatSpendDisplay renders a USD amount as "$X.YY (estimated A.AA% of $1100)",
// the percentage being the amount's share of the monthly budget. Both the dollar
// amount and the percentage are shown to 2 decimal places.
func formatSpendDisplay(usd float64) string {
	pct := 0.0
	if MonthlyBudgetUSD > 0 {
		pct = usd / MonthlyBudgetUSD * 100
	}
	return fmt.Sprintf("$%.2f (estimated %.2f%% of $%.0f)", usd, pct, MonthlyBudgetUSD)
}
