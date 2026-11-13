"""Accessible page shell; all provider/checklist data comes from the API."""

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Onboard HQ</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; background: #f4f6f8;
      color: #172b3a; line-height: 1.5; }
    main { max-width: 1000px; margin: auto; padding: 24px; }
    section { background: white; border: 1px solid #cbd5df; border-radius: 8px;
      padding: 20px; margin: 20px 0; }
    h1, h2, h3, h4 { line-height: 1.25; }
    h2 { font-size: 1.25rem; margin-top: 0; }
    .section-heading { display: flex; justify-content: space-between;
      align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
    .section-heading h2 { margin-bottom: 0; }
    .section-heading button { margin-left: auto; }
    h3 { font-size: 1.1rem; }
    h4 { margin: 0 0 12px; }
    label { display: block; font-weight: 600; margin-bottom: 6px; }
    input, select, textarea, button { font: inherit; padding: 9px; max-width: 100%; }
    select, textarea, input[type="text"], input[type="date"] { width: 100%; }
    textarea { min-height: 110px; resize: vertical; }
    button { cursor: pointer; border: 1px solid #788f9b; border-radius: 5px;
      color: #172b3a; background: #f1f6f8; }
    button.primary { color: white; background: #205f79; border-color: #205f79; }
    button:disabled { cursor: default; opacity: .6; }
    :focus-visible { outline: 3px solid #3088ac; outline-offset: 3px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
    .table-scroll { max-width: 100%; overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; min-width: 540px; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #dde5e9; }
    table[aria-label="Onboarding checklist"] { min-width: 760px; }
    table[aria-label="Onboarding checklist"] thead { background: #205f79; color: white; }
    .requirement-row td { border-bottom-color: #bdcfd9; vertical-align: top; }
    .requirement-row.stripe-even { background: #edf4f8; }
    .requirement-row.editing { box-shadow: inset 4px 0 #205f79; }
    .editing-label { display: block; font-weight: 600; color: #205f79; }
    .status-badge { display: inline-block; padding: 3px 10px; border-radius: 999px;
      font-weight: 600; max-width: 240px; overflow-wrap: anywhere; }
    .status-badge:not(.status-unknown) { white-space: nowrap; }
    .status-finished { background: #ddf3e6; color: #185b36; }
    .status-progress { background: #dceefa; color: #174e78; }
    .status-attention { background: #fff0cc; color: #765000; }
    .status-unknown { background: #e9edf0; color: #354c5a; }
    .checklist-fields { min-width: 0; margin: 4px 0; padding: 14px;
      border: 1px solid #9bb7c7; border-radius: 6px; background: #f5f8fa; }
    .checklist-edit-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .manual-change { background: #fff2cc; padding: 6px; }
    .manual-change-label { display: block; font-size: .85rem; margin-top: 6px; }
    #checklist-status:empty { display: none; }
    #review-disclosure > summary { cursor: pointer; }
    #review-disclosure > summary h2 { display: inline; }
    #pending-suggestions { display: inline-block; color: #425d6b; margin-left: 10px; }
    #review-results { margin-top: 20px; }
    p, li, blockquote { overflow-wrap: anywhere; }
    blockquote { margin: 12px 0; padding: 10px 14px; border-left: 3px solid #a9bfca;
      background: #f5f8fa; white-space: pre-wrap; }
    .suggestion { border-top: 1px solid #cbd5df; padding: 18px 0; }
    .update { padding-bottom: 16px; border-bottom: 2px solid #dce5ea; }
    .review-fields { border: 1px solid #cbd5df; background: #f5f8fa;
      border-radius: 6px; padding: 14px; margin-top: 14px; min-width: 0; }
    .review-table { min-width: 620px; table-layout: fixed; }
    .review-table th:nth-child(1) { width: 23%; }
    .review-table th:nth-child(2) { width: 29%; }
    .review-table th:nth-child(3) { width: 30%; }
    .review-table th:nth-child(4) { width: 18%; }
    .review-table td { vertical-align: top; overflow-wrap: anywhere; }
    .review-table .review-change { background: #fff2cc; box-shadow: inset 0 3px #ad7513; }
    .review-saved, .review-original, .review-change-label { display: block; font-size: .85rem; }
    .review-saved { color: #425d6b; margin-bottom: 8px; }
    .review-original { color: #425d6b; margin-top: 5px; }
    .review-change-label { font-weight: 600; margin-top: 7px; }
    .review-invalid .review-change-label { color: #8b2e23; }
    .confirmation { display: flex; gap: 8px; align-items: center; margin-top: 14px; }
    .notice { color: #425d6b; }
    .provider-form { margin-top: 18px; }
    .provider-form fieldset { min-width: 0; border: 1px solid #cbd5df;
      border-radius: 6px; padding: 16px; background: #f5f8fa; }
    .provider-form legend { font-weight: 600; }
    .provider-create-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .provider-name-field { grid-column: 1 / -1; }
    .provider-field-label { display: block; font-weight: 600; margin-bottom: 6px; }
    #provider-creation-status:empty { display: none; }
    .monitoring-counts { display: grid; grid-template-columns: repeat(4, 1fr);
      gap: 12px; margin: 16px 0; }
    .monitoring-counts div { background: #f1f6f8; border: 1px solid #dce5ea;
      border-radius: 6px; padding: 12px; }
    .monitoring-counts dt { color: #425d6b; }
    .monitoring-counts dd { font-size: 1.6rem; font-weight: 700; margin: 4px 0 0; }
    .indicator { font-weight: 600; }
    .indicator.finished { color: #236044; }
    .indicator.overdue, .indicator.needs_review { color: #82401a; }
    #request-status { min-height: 1.5em; }
    @media (max-width: 600px) {
      main { padding: 14px; } section { padding: 16px; }
      .provider-create-grid { grid-template-columns: 1fr; }
      .checklist-edit-grid { grid-template-columns: 1fr; }
      .checklist-fields { max-width: calc(100vw - 100px); }
      .monitoring-counts { grid-template-columns: repeat(2, 1fr); }
    }
  </style>
  <script src="/static/onboarding.js" type="module"></script>
</head>
<body>
<main>
  <h1>Onboard HQ</h1>
  <p>Provider onboarding dashboard</p>
  <p class="notice"><strong>Prototype:</strong> Use fictional providers and synthetic updates only. Updates,
    suggestions, and change history are saved. Only a manager can save checklist changes.</p>
  <section aria-labelledby="role-heading">
    <h2 id="role-heading">Demo role</h2>
    <label for="demo-role">Simulated role</label>
    <select id="demo-role"><option value="proposer">Proposer</option><option value="manager">Manager</option></select>
    <p class="notice">Anyone can propose an update. Manager mode can add providers, edit checklist
      statuses and dates, and approve, correct, or reject suggestions. This switch simulates a role; it does not verify identity.</p>
  </section>
  <section aria-labelledby="provider-heading">
    <div class="section-heading"><h2 id="provider-heading">1. Select a provider</h2>
      <button id="add-provider" type="button" hidden>Add provider</button></div>
    <label for="provider">Provider</label>
    <select id="provider" disabled><option>Loading providers…</option></select>
    <p id="provider-description"></p>
    <div class="actions">
      <button id="refresh-data" type="button">Refresh data</button>
    </div>
    <form id="provider-form" class="provider-form" aria-label="Add provider" hidden>
      <fieldset id="provider-fields">
        <legend>Add fictional provider</legend>
        <p class="notice">Use a fictional name for this prototype. The selected type's requirements start Outstanding.</p>
        <div class="provider-create-grid">
          <div class="provider-name-field"><label for="new-provider-name">Provider name</label>
            <input id="new-provider-name" type="text" required placeholder="Dr. Avery Example"></div>
          <div id="provider-type-single" hidden><span class="provider-field-label">Provider type</span><p id="provider-type-name"></p></div>
          <div id="provider-type-picker" hidden><label for="new-provider-type">Provider type</label><select id="new-provider-type"></select></div>
          <div><label for="new-provider-start">Proposed start date (optional)</label><input id="new-provider-start" type="date"></div>
        </div>
        <p id="provider-template-count" class="notice"></p>
        <div id="provider-preview" class="table-scroll" tabindex="0" role="region" aria-label="Scrollable provider checklist preview" hidden>
          <table aria-label="New provider checklist preview">
            <thead><tr><th scope="col">Requirement</th><th scope="col">Status</th><th scope="col">Requirement date</th><th scope="col">Deadline</th></tr></thead>
            <tbody id="provider-preview-rows"></tbody>
          </table>
        </div>
        <div class="actions"><button id="save-provider" type="submit" class="primary" disabled>Add provider</button><button id="cancel-provider" type="button">Cancel</button></div>
      </fieldset>
    </form>
    <p id="provider-creation-status" role="status" aria-live="polite"></p>
  </section>
  <section aria-labelledby="checklist-heading">
    <h2 id="checklist-heading">2. Onboarding checklist</h2>
    <div id="monitoring-summary" role="region" aria-label="Monitoring summary" hidden>
      <dl class="monitoring-counts">
        <div><dt>Finished</dt><dd aria-label="Finished" id="count-finished"></dd></div>
        <div><dt>Remaining</dt><dd aria-label="Remaining" id="count-remaining"></dd></div>
        <div><dt>Overdue</dt><dd aria-label="Overdue" id="count-overdue"></dd></div>
        <div><dt>Needs review</dt><dd aria-label="Needs review" id="count-needs_review"></dd></div>
      </dl>
      <p id="monitoring-as-of" class="notice"></p>
      <p class="notice">Remaining includes uncertain items. Needs review means the saved
        status, requirement, or provider type has no recognized completion rule;
        it does not mean a suggestion is awaiting approval.</p>
    </div>
    <p id="empty-checklist" hidden>No checklist requirements are saved for this provider.</p>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable checklist">
      <table aria-label="Onboarding checklist">
        <thead><tr><th scope="col">Requirement</th><th scope="col">Status</th>
          <th scope="col">Requirement date</th><th scope="col">Deadline</th>
          <th scope="col">Monitoring</th><th scope="col" id="checklist-action-heading" hidden>Action</th></tr></thead>
        <tbody id="requirements"></tbody>
      </table>
    </div>
    <p id="checklist-status" role="status" aria-live="polite"></p>
    <button type="button" id="retry-checklist" hidden>Retry checklist save</button>
  </section>
  <section aria-labelledby="update-heading">
    <h2 id="update-heading">3. Updates</h2>
    <form id="update-form" action="/updates/analyze" method="post">
      <label for="update-text">Original update</label>
      <textarea id="update-text" required placeholder="Enter a synthetic onboarding update"></textarea>
      <div class="actions"><button class="primary" id="submit-update" type="submit" disabled>Analyze update</button></div>
    </form>
    <p id="request-status" role="status" aria-live="polite">Loading saved data…</p>
  </section>
  <section aria-labelledby="review-heading">
    <details id="review-disclosure">
      <summary><h2 id="review-heading">4. Suggestions and review history</h2>
        <span id="pending-suggestions">0 pending suggestions</span></summary>
      <div id="review-results"></div>
    </details>
  </section>
</main>
</body>
</html>
"""
