// Public synthetic data/controller for an explicitly copied browser fixture. No network or wallet operations.
import { PaperWorkerClosedError, type PaperAPI } from '@/lib/probes/paper-api';
import type { ColonyRun } from '@/lib/probes/types';

export const PAPER_FIXTURE_SOURCE_RECEIPTS = {"assessment": "af375fff4c35e02f12c93836563dd17d18e6d71b0450921d7d4d54016ac41b20", "exactTrade": "3f971dfa68f8763d282470d8a2b26e2eca750c72208cd8c09bce64510beb9d0f"} as const;

const ASSESSMENT = {
  "probes": [
    {
      "id": "00000000-0000-0000-0000-000000000010",
      "name": "Synthetic-0-0",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.8000000000000p+1",
        "ema_slow": "0x1.4000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100.07",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000010",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000011",
      "name": "Synthetic-0-1",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.0000000000000p+2",
        "ema_slow": "0x1.5000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000011",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000012",
      "name": "Synthetic-0-2",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.4000000000000p+2",
        "ema_slow": "0x1.6000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000012",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000013",
      "name": "Synthetic-0-3",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.8000000000000p+2",
        "ema_slow": "0x1.7000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000013",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000014",
      "name": "Synthetic-0-4",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.c000000000000p+2",
        "ema_slow": "0x1.8000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000014",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000015",
      "name": "Synthetic-0-5",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.0000000000000p+3",
        "ema_slow": "0x1.9000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000015",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000016",
      "name": "Synthetic-0-6",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.2000000000000p+3",
        "ema_slow": "0x1.a000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000016",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000017",
      "name": "Synthetic-0-7",
      "generation": 0,
      "genome": {
        "ema_fast": "0x1.4000000000000p+3",
        "ema_slow": "0x1.b000000000000p+4",
        "generation": 0,
        "parent_ids": []
      },
      "initial_cash": "100",
      "economic_cash": "0",
      "retired": true,
      "terminal_cash": "100",
      "equity": null,
      "equity_basis": "terminal_frozen",
      "metrics_basis": "last_observed_before_replacement",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000017",
        "strategy": "genetic_algorithm",
        "operation": "founder",
        "source_iteration_id": null,
        "offspring_index": null,
        "distribution_id": null,
        "sources": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000018",
      "name": "Synthetic-1-0",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.8000000000000p+1",
        "ema_slow": "0x1.4000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000018",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 0,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000019",
      "name": "Synthetic-1-1",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.0000000000000p+2",
        "ema_slow": "0x1.5000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000019",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 1,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000020",
      "name": "Synthetic-1-2",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.4000000000000p+2",
        "ema_slow": "0x1.6000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000020",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 2,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000021",
      "name": "Synthetic-1-3",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.8000000000000p+2",
        "ema_slow": "0x1.7000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000021",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 3,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000022",
      "name": "Synthetic-1-4",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.c000000000000p+2",
        "ema_slow": "0x1.8000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000022",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 4,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000023",
      "name": "Synthetic-1-5",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.0000000000000p+3",
        "ema_slow": "0x1.9000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000023",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 5,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000024",
      "name": "Synthetic-1-6",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.2000000000000p+3",
        "ema_slow": "0x1.a000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000024",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 6,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000025",
      "name": "Synthetic-1-7",
      "generation": 1,
      "genome": {
        "ema_fast": "0x1.4000000000000p+3",
        "ema_slow": "0x1.b000000000000p+4",
        "generation": 1,
        "parent_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011"
        ]
      },
      "initial_cash": "100",
      "economic_cash": "100",
      "retired": false,
      "terminal_cash": null,
      "equity": "100",
      "equity_basis": "reference_mark",
      "metrics_basis": "checkpoint_member",
      "peak_equity": "100.09",
      "max_drawdown": {
        "numerator": "9",
        "denominator": "10000"
      },
      "closed_trades": 0,
      "account_currency": "USD",
      "lineage": {
        "version": 1,
        "child_id": "00000000-0000-0000-0000-000000000025",
        "strategy": "genetic_algorithm",
        "operation": "crossover_mutation",
        "source_iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "offspring_index": 7,
        "distribution_id": null,
        "sources": [
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "ordinal": 0
          },
          {
            "role": "genetic_parent",
            "source_id": "00000000-0000-0000-0000-000000000011",
            "ordinal": 1
          }
        ]
      }
    }
  ],
  "evaluations": [
    {
      "account_currency": "USD",
      "scoring_policy": "tagged_worker_evaluation_v1",
      "cohort": {
        "iteration_id": "00000000-0000-0000-0000-000000000002:0",
        "policy": {
          "version": "common-market-window-v1"
        },
        "phase": "completed",
        "member_ids": [
          "00000000-0000-0000-0000-000000000010",
          "00000000-0000-0000-0000-000000000011",
          "00000000-0000-0000-0000-000000000012",
          "00000000-0000-0000-0000-000000000013",
          "00000000-0000-0000-0000-000000000014",
          "00000000-0000-0000-0000-000000000015",
          "00000000-0000-0000-0000-000000000016",
          "00000000-0000-0000-0000-000000000017"
        ],
        "member_count": 8,
        "completed_count": 8,
        "horizon_seconds": {
          "float64": "0x1.c200000000000p+11"
        },
        "started_at": {
          "float64": "0x1.3880000000000p+13"
        },
        "ends_at": {
          "float64": "0x1.a900000000000p+13"
        },
        "completed_at": {
          "float64": "0x1.a900000000000p+13"
        },
        "abort_reason": null,
        "evaluations": [
          {
            "probe_id": "00000000-0000-0000-0000-000000000010",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:0",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "-0x1.205bc01a36e2fp-10"
            },
            "roi": {
              "float64": "0x1.6f0068db8bac7p-11"
            },
            "num_trades": 1,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000011",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:1",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000012",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:2",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000013",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:3",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000014",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:4",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000015",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:5",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000016",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:6",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000017",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:0:7",
            "iteration_id": "00000000-0000-0000-0000-000000000002:0",
            "fitness": {
              "float64": "0x0.0p+0"
            },
            "roi": {
              "float64": "0x0.0p+0"
            },
            "num_trades": 0,
            "reason": "window_complete",
            "status": "completed",
            "cohort_complete": true,
            "window_started_at": {
              "float64": "0x1.3880000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "terminated_at": {
              "float64": "0x1.a900000000000p+13"
            }
          }
        ]
      },
      "selection": {
        "selection_policy": "completed-window-generational-ga-v1"
      }
    },
    {
      "account_currency": "USD",
      "scoring_policy": "tagged_worker_evaluation_v1",
      "cohort": {
        "iteration_id": "00000000-0000-0000-0000-000000000002:1",
        "policy": {
          "version": "common-market-window-v1"
        },
        "phase": "aborted",
        "member_ids": [
          "00000000-0000-0000-0000-000000000018",
          "00000000-0000-0000-0000-000000000019",
          "00000000-0000-0000-0000-000000000020",
          "00000000-0000-0000-0000-000000000021",
          "00000000-0000-0000-0000-000000000022",
          "00000000-0000-0000-0000-000000000023",
          "00000000-0000-0000-0000-000000000024",
          "00000000-0000-0000-0000-000000000025"
        ],
        "member_count": 8,
        "completed_count": 0,
        "horizon_seconds": {
          "float64": "0x1.c200000000000p+11"
        },
        "started_at": {
          "float64": "0x1.a900000000000p+13"
        },
        "ends_at": {
          "float64": "0x1.0cc0000000000p+14"
        },
        "completed_at": {
          "float64": "0x1.a950000000000p+13"
        },
        "abort_reason": "stopped",
        "evaluations": [
          {
            "probe_id": "00000000-0000-0000-0000-000000000018",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:0",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000019",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:1",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000020",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:2",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000021",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:3",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000022",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:4",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000023",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:5",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000024",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:6",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          },
          {
            "probe_id": "00000000-0000-0000-0000-000000000025",
            "evaluation_id": "00000000-0000-0000-0000-000000000002:1:7",
            "iteration_id": "00000000-0000-0000-0000-000000000002:1",
            "fitness": null,
            "roi": null,
            "num_trades": 0,
            "reason": "stopped",
            "status": "aborted",
            "cohort_complete": false,
            "window_started_at": {
              "float64": "0x1.a900000000000p+13"
            },
            "window_ends_at": {
              "float64": "0x1.0cc0000000000p+14"
            },
            "terminated_at": {
              "float64": "0x1.a950000000000p+13"
            }
          }
        ]
      },
      "selection": null
    }
  ],
  "execution_policy": {
    "version": "usd-reference-decimal-v2",
    "account_currency": "USD",
    "cost_assumptions": "uncalibrated_scenario",
    "config": {
      "fee_bps": "0",
      "slippage_bps": "0",
      "half_spread_bps": "0"
    }
  }
};
const EXACT_TRADE = {
  "open": {
    "source": "synthetic exact ledger fixture: EntryPlan(25,123.45,zero costs), ExitPlan(124); usd-reference-decimal-v2",
    "id": "00000000-0000-0000-0000-000000000003",
    "account_id": "00000000-0000-0000-0000-000000000001",
    "asset": "SOL/USD",
    "account_currency": "USD",
    "quantity": "0.202511138112596192",
    "closed": false,
    "opened_at": "2026-10-08T00:00:01Z",
    "closed_at": null,
    "exit_reason": null,
    "exit": null,
    "entry": {
      "version": "usd-reference-decimal-v2",
      "config": {
        "fee_bps": "0",
        "half_spread_bps": "0",
        "slippage_bps": "0"
      },
      "budget": "25",
      "reference_price": "123.45",
      "fill_price": "123.45",
      "quantity": "0.202511138112596192",
      "notional": "24.9999999999999999024",
      "fee": "0",
      "cash_debit": "24.9999999999999999024",
      "residual_budget": "0.0000000000000000976"
    }
  },
  "closed": {
    "source": "synthetic exact ledger fixture: EntryPlan(25,123.45,zero costs), ExitPlan(124); usd-reference-decimal-v2",
    "id": "00000000-0000-0000-0000-000000000003",
    "account_id": "00000000-0000-0000-0000-000000000001",
    "asset": "SOL/USD",
    "account_currency": "USD",
    "quantity": "0.202511138112596192",
    "closed": true,
    "opened_at": "2026-10-08T00:00:01Z",
    "closed_at": "2026-10-08T00:15:01Z",
    "exit_reason": "exit_signal",
    "exit": {
      "version": "usd-reference-decimal-v2",
      "entry": {
        "version": "usd-reference-decimal-v2",
        "config": {
          "fee_bps": "0",
          "half_spread_bps": "0",
          "slippage_bps": "0"
        },
        "budget": "25",
        "reference_price": "123.45",
        "fill_price": "123.45",
        "quantity": "0.202511138112596192",
        "notional": "24.9999999999999999024",
        "fee": "0",
        "cash_debit": "24.9999999999999999024",
        "residual_budget": "0.0000000000000000976"
      },
      "kind": "fill",
      "reference_price": "124",
      "fill_price": "124",
      "quantity": "0.202511138112596192",
      "notional": "25.111381125961927808",
      "fee": "0",
      "cash_credit": "25.111381125961927808",
      "gross_pnl": "0.1113811259619279056",
      "net_pnl": "0.1113811259619279056"
    },
    "entry": {
      "version": "usd-reference-decimal-v2",
      "config": {
        "fee_bps": "0",
        "half_spread_bps": "0",
        "slippage_bps": "0"
      },
      "budget": "25",
      "reference_price": "123.45",
      "fill_price": "123.45",
      "quantity": "0.202511138112596192",
      "notional": "24.9999999999999999024",
      "fee": "0",
      "cash_debit": "24.9999999999999999024",
      "residual_budget": "0.0000000000000000976"
    }
  }
};

export const PAPER_FIXTURE_ACTORS = {
  alice: { owner: '10000000-0000-4000-8000-000000000001', prefix: 'a', label: 'ALICE' },
  bob: { owner: '20000000-0000-4000-8000-000000000002', prefix: 'b', label: 'BOB' },
} as const;
export type PaperFixtureScenario = 'normal' | 'closed-worker' | 'lost-start-ack' | 'pending-start'
  | 'lost-stop-ack' | 'pending-stop' | 'read-error' | 'oversized-read' | 'unknown-version'
  | 'unknown-policy' | 'worker-turnover';
export const PAPER_FIXTURE_SCENARIOS: PaperFixtureScenario[] = ['normal', 'closed-worker', 'lost-start-ack',
  'pending-start', 'lost-stop-ack', 'pending-stop', 'read-error', 'oversized-read', 'unknown-version',
  'unknown-policy', 'worker-turnover'];
const TEMPLATE_RUN = '00000000-0000-0000-0000-000000000002';
const MAX_TRACE = 512, MAX_PENDING = 8, GATE_TIMEOUT_MS = 90_000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Synthetic argument refusal');
  return value as Record<string, unknown>;
}
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const item of Object.values(value)) freeze(item);
    Object.freeze(value);
  }
  return value;
}
freeze(ASSESSMENT); freeze(EXACT_TRADE);
export type PaperFixtureTrace = {
  sequence: number; owner: string; kind: 'read' | 'worker' | 'legacy'; action: string;
  run: string | null; requestId: string | null; projection: string | null;
};
export type PaperFixturePending = { id: string; trace: PaperFixtureTrace; signalAborted: boolean };
type Gate = { id: string; trace: PaperFixtureTrace; signal?: AbortSignal; abortListener?: () => void;
  value: unknown; resolve: (value: unknown) => void; reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout> };

/** Stable APIOverride with owner-bound, captured responses and explicit promise barriers. */
export function createPaperFixtureController(owner: string) {
  const candidate = Object.values(PAPER_FIXTURE_ACTORS).find(actor => actor.owner === owner);
  if (!candidate) throw Error('Only the synthetic paper actors are admitted');
  const actor = candidate;
  const uuid = (digit: string) => `${actor.prefix}${digit}000000-0000-4000-8000-000000000001`;
  const historyRun = uuid('1'), pilotRun = uuid('2');
  const originalStart = uuid('3'), originalStop = uuid('4');
  const traces: PaperFixtureTrace[] = [], gates = new Map<string, Gate>(), listeners = new Set<() => void>();
  const holds: { kind: 'read' | 'worker'; action: string }[] = [];
  const archived = new Map<string, Record<string, unknown>>();
  let scenario: PaperFixtureScenario = 'normal', phase = 'fresh', stopRequested = false;
  let controlRun = pilotRun, controlStart = originalStart, controlStop = originalStop, disposed = false;
  const notify = () => { if (!disposed) for (const listener of listeners) listener(); };
  const state = () => ({ version: 1, owner_id: owner, run_id: controlRun, request_id: controlStart,
    phase, busy: false, stop_requested: stopRequested,
    requires_reconciliation: ['pending', 'drained', 'failed', 'stopped'].includes(phase) });
  function trace(kind: PaperFixtureTrace['kind'], action: string, args: Record<string, unknown>) {
    if (disposed || traces.length >= MAX_TRACE) throw Error('Synthetic fixture request bound');
    const entry = { sequence: traces.length + 1, owner, kind, action,
      run: typeof args.run === 'string' ? args.run : kind === 'worker' ? controlRun : null,
      requestId: typeof args.request_id === 'string' ? args.request_id : null,
      projection: typeof args.kind === 'string' ? args.kind : null };
    traces.push(entry); notify(); return entry;
  }
  function finish(id: string, rejected = false) {
    const gate = gates.get(id);
    if (!gate) return false;
    gates.delete(id); clearTimeout(gate.timer);
    gate.signal?.removeEventListener('abort', gate.abortListener!);
    if (rejected) gate.reject(Error('Synthetic fixture rejected its captured response'));
    else gate.resolve(structuredClone(gate.value));
    notify(); return true;
  }
  function deliver(entry: PaperFixtureTrace, value: unknown, signal?: AbortSignal) {
    const captured = freeze(structuredClone(value));
    const index = holds.findIndex(hold => hold.kind === entry.kind && hold.action === entry.action);
    if (index < 0) return Promise.resolve(structuredClone(captured));
    holds.splice(index, 1);
    if (gates.size >= MAX_PENDING) return Promise.reject(Error('Synthetic fixture pending bound'));
    const id = `${owner}:${entry.sequence}`;
    return new Promise<unknown>((resolve, reject) => {
      const gate: Gate = { id, trace: entry, signal, value: captured, resolve, reject,
        timer: setTimeout(() => finish(id, true), GATE_TIMEOUT_MS) };
      // Intentionally retain the captured reply after abort so the browser can release an
      // original-owner callback explicitly. Real component deadline/session guards still run.
      gate.abortListener = notify;
      signal?.addEventListener('abort', gate.abortListener, { once: true });
      gates.set(id, gate); notify();
    });
  }
  function details(run: string) {
    const data = JSON.parse(JSON.stringify(ASSESSMENT).replaceAll(TEMPLATE_RUN, run)) as typeof ASSESSMENT;
    data.probes.forEach(probe => { probe.name = `${actor.label} PRIVATE ${probe.name}`; });
    if (scenario === 'unknown-policy') {
      for (const evaluation of data.evaluations) {
        evaluation.cohort.policy.version = 'future-window-v9';
        evaluation.scoring_policy = 'future-score-v2';
      }
    }
    return data;
  }
  function runData(run: string) {
    return { id: run, durability_version: scenario === 'unknown-version' ? 99 : 5, account_currency: 'USD',
      initial_cash: '1000', reserve: '200', reference_equity: '1000.07', status: 'stopped', generation: 1,
      open_position_count: 1, requires_reconciliation: true,
      committed_at: '2026-10-08T12:00:00Z', source_at: '2026-10-08T11:59:00Z',
      execution_policy: structuredClone(ASSESSMENT.execution_policy), fixture_actor: actor.label };
  }
  const api: PaperAPI = {
    async read(name, rawArgs, signal) {
      const args = object(rawArgs), entry = trace('read', name, args);
      if (!['discover', 'page', 'events', 'archive_run'].includes(name)) throw Error('Synthetic RPC refusal');
      if (scenario === 'read-error') throw Error('Synthetic history failure');
      const knownRun = (value: unknown) => {
        if (value !== historyRun && value !== pilotRun) throw Error('Synthetic owner/run refusal');
        return value as string;
      };
      if (name === 'discover') {
        const records = [historyRun, pilotRun].map(run => ({ run_id: run, revision: 3,
          data: runData(run), archive_receipt: archived.get(run) ?? null }));
        return deliver(entry, { version: 1, owner_id: owner, through_id: pilotRun, records,
          next_id: pilotRun, has_more: false }, signal);
      }
      const run = knownRun(args.run);
      if (name === 'archive_run') {
        if (typeof args.request_id !== 'string' || !UUID.test(args.request_id) || args.expected_revision !== 3) throw Error('Synthetic archive refusal');
        const receipt = { owner_id: owner, run_id: run, request_id: args.request_id,
          revision: 3, archived: true };
        archived.set(run, receipt); return deliver(entry, receipt, signal);
      }
      if (name === 'events') {
        const event = { sequence: 1, revision: 3, command_id: originalStart,
          data: { event_id: `${run}:${originalStart}:0`, event_index: 0,
            event: { type: 'run_status', status: 'stopped', fixture_actor: actor.label } } };
        return deliver(entry, { version: 1, owner_id: owner, run_id: run, through_sequence: 1,
          records: [event], has_more: false, next_sequence: 1 }, signal);
      }
      const data = details(run);
      const rows = args.kind === 'runs' ? [runData(run)] : args.kind === 'probes' ? data.probes
        : args.kind === 'trades' ? [EXACT_TRADE.open, EXACT_TRADE.closed]
          : args.kind === 'evaluations' ? data.evaluations : args.kind === 'samples' ? [] : null;
      if (rows === null) throw Error('Synthetic projection refusal');
      const records = rows.map((value, index) => ({ revision: args.kind === 'trades' ? index + 2 : 3,
        key: args.kind === 'evaluations' ? data.evaluations[index].cohort.iteration_id
          : args.kind === 'trades' ? `${EXACT_TRADE.open.id}:0000` : String(object(value).id),
        command_id: originalStart, data: structuredClone(value) }));
      if (scenario === 'oversized-read' && args.kind === 'runs') Object.assign(records[0].data, { padding: 'x'.repeat(65_537) });
      return deliver(entry, { version: 1, owner_id: owner, run_id: run, kind: args.kind,
        through_revision: 3, records, has_more: false,
        next_cursor: records.length ? { revision: records.at(-1)!.revision, key: records.at(-1)!.key } : null }, signal);
    },
    async worker(name, rawArgs, signal) {
      const args = rawArgs === undefined ? {} : object(rawArgs), entry = trace('worker', name, args);
      if (scenario === 'closed-worker') throw new PaperWorkerClosedError();
      if (name === 'status') return deliver(entry, state(), signal);
      if (name === 'controls') return deliver(entry, { version: 1, owner_id: owner,
        run_id: controlRun, start_id: controlStart, stop_id: controlStop }, signal);
      if (!['start', 'stop', 'settle'].includes(name) || Object.keys(args).length !== 1
        || args.request_id !== (name === 'stop' ? controlStop : controlStart)) throw Error('Synthetic original control ID refusal');
      if (name === 'stop') stopRequested = true;
      if ((name === 'start' && scenario === 'lost-start-ack') || (name === 'stop' && scenario === 'lost-stop-ack')) {
        phase = 'pending'; notify(); throw Error('Synthetic lost acknowledgment');
      }
      if ((name === 'start' && scenario === 'pending-start') || (name === 'stop' && scenario === 'pending-stop')) phase = 'pending';
      else phase = name === 'stop' || stopRequested ? 'stopped' : 'running';
      return deliver(entry, state(), signal);
    },
  };
  const legacyReader = async (requestedOwner: string, signal?: AbortSignal): Promise<ColonyRun[]> => {
    if (requestedOwner !== owner || signal?.aborted) throw Error('Synthetic legacy owner refusal');
    trace('legacy', 'history', {});
    return [{ run_id: uuid('5'), mode: 'simulation', strategy: 'legacy-fixture',
      history_source: 'colony', started_at: '2026-01-01T00:00:00Z', ended_at: '2026-01-02T00:00:00Z',
      probe_count: 8, best_fitness: 0.012, status: 'stopped',
      runtime: { open_positions: 1, requires_reconciliation: true } }];
  };
  return {
    owner, label: actor.label, historyRun, pilotRun, originalStart, originalStop, api, legacyReader,
    snapshot() { return { owner, label: actor.label, scenario, phase, stopRequested, controlRun,
      traces: structuredClone(traces), holds: structuredClone(holds),
      pending: [...gates.values()].map(gate => ({ id: gate.id, trace: gate.trace, signalAborted: gate.signal?.aborted ?? false })) }; },
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    setScenario(next: PaperFixtureScenario) {
      if (!PAPER_FIXTURE_SCENARIOS.includes(next)) throw Error('Synthetic scenario refusal');
      scenario = next;
      if (next === 'worker-turnover') { controlRun = uuid('9'); controlStart = uuid('7'); controlStop = uuid('8'); }
      if (next === 'pending-stop' || next === 'lost-stop-ack') phase = 'running';
      notify();
    },
    resetWorker() { scenario = 'normal'; phase = 'fresh'; stopRequested = false;
      controlRun = pilotRun; controlStart = originalStart; controlStop = originalStop; notify(); },
    holdNext(kind: 'read' | 'worker', action: string) {
      if (holds.length >= MAX_PENDING || !((kind === 'read' && ['discover', 'page', 'events', 'archive_run'].includes(action))
        || (kind === 'worker' && ['status', 'controls', 'start', 'stop', 'settle'].includes(action)))) throw Error('Synthetic hold refusal');
      holds.push({ kind, action }); notify();
    },
    release: (id: string) => finish(id), reject: (id: string) => finish(id, true),
    dispose() { for (const id of [...gates.keys()]) finish(id, true); listeners.clear(); holds.length = 0; disposed = true; },
  };
}
export type PaperFixtureController = ReturnType<typeof createPaperFixtureController>;
