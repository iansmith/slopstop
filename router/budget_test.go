package main

import "testing"

func TestMonthlyBudgetConstant(t *testing.T) {
	if MonthlyBudgetUSD != 1100.0 {
		t.Errorf("MonthlyBudgetUSD = %v, want 1100.0", MonthlyBudgetUSD)
	}
}

func TestFormatSpendDisplay(t *testing.T) {
	cases := []struct {
		name string
		usd  float64
		want string
	}{
		{"one percent", 11.00, "$11.00 (estimated 1.00% of $1100)"},
		{"half percent", 5.50, "$5.50 (estimated 0.50% of $1100)"},
		{"quarter percent", 2.75, "$2.75 (estimated 0.25% of $1100)"},
		{"rounds sub-cent dollar to zero", 0.004, "$0.00 (estimated 0.00% of $1100)"},
		{"rounds tiny percent to zero", 0.01, "$0.01 (estimated 0.00% of $1100)"},
		{"zero", 0, "$0.00 (estimated 0.00% of $1100)"},
		{"full budget", 1100.0, "$1100.00 (estimated 100.00% of $1100)"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := formatSpendDisplay(tc.usd); got != tc.want {
				t.Errorf("formatSpendDisplay(%v) = %q, want %q", tc.usd, got, tc.want)
			}
		})
	}
}
