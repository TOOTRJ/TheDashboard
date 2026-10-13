# Dialog focus recovery and sample action acceptance

The compiled synthetic browser fixture at app commit d16c8ee revealed an actual
dialog-closing defect. After Escape closed Sample Trade Details, its body was
cleared but a visible 512×68px dialog remained with data-state=closed. The
header remained aria-hidden=true, so its account control was inaccessible to
keyboard navigation. A subsequent observation still saw this state.

The dialog's computed animation was focus-pulse, duration 2s, running infinitely.
The global *:focus-visible rule applied that animation to focused modal content.
The installed Radix Presence implementation suspends unmounting when an exit
animation begins and waits for animationend/animationcancel. The global infinite
focus animation could take precedence over the dialog's finite exit animation.
[Radix animation behavior](https://www.radix-ui.com/primitives/docs/guides/animation).

The repair retains the static cyan keyboard outline and offset, removing only
the global animation and its unused keyframes. It changes no dialog state,
receipt, transaction, data fetch or timer policy. Finite component entrance/exit
animations remain. Real browser closure, modal removal and focus recovery must
be observed after a fresh build; a controlled React callback alone is insufficient.

The existing mouse-open sample rows also lacked keyboard-accessible triggers.
Each asset cell now contains a native button with an explicit sample-details
label and dialog popup semantics. Its click stops propagation before selecting
the same existing sample item. The row's mouse behavior, sorting, filtering and
pagination are preserved. A DialogDescription identifies the fictional example
for assistive technology. Copy and Explorer remain disabled with their reasons.

Sidebar trading-status honesty is part of this bounded follow-up. It must not
claim an enabled paid trading mode or offer an inert interactive promotion.
Normal navigation, sidebar toggles and demo market provenance remain available.

The pre-repair fixture passed real sample labels, keyboard range choices and
pagination/sort controls, combined activity filters, and fictional details with
disabled Copy/Explorer. Its stuck closure and selector failures remain dated
evidence; they are not acceptance of the repair. The earlier wrong uppercase
login-field selector was corrected after reading actual DOM labels. No hosted
account, provider, database or trading action was used. Full audit/accessibility
acceptance remains separate from this focused browser flow.

The five complete existing Home controlled cases pass, zero skips, in
1280.948125 ms; the new native trigger handler/description is exercised without
claiming DOM focus or animation behavior. Full TypeScript checking and scoped
Activity/Sidebar/test ESLint pass with no warnings or errors. New browser
acceptance remains pending. The React
review checklist is applied to component boundaries, native accessible controls,
event semantics and preserved data flow; no optimization or dependency change
is needed for these defects.

Reviewed source pins for the fresh-build acceptance:

- `src/app/globals.css`: `df69e76b71faacec570c9a0d9fc61234e718d0bc031bbf1fdc042ed3b2a9ed6d`.
- `src/components/dashboard/ActivityTable.tsx`: `fd723a3c7a6a0511cbe2a3f3478037768bd665db50c5fec41d90ba46245ec594`.
- `src/components/layout/Sidebar.tsx`: `f44736b0f57e9a96c65c2bf566efd3ee0cc4ffdd24dfb8b46e98d37ab9fd7f76`.
- `tests/home-sample-provenance.test.mjs`: `a400a271703f81b7c2aaadca05da7cfde583e61679e86d8473eeb62ca1653f85`.
