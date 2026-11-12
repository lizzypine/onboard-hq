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
    p, li, blockquote { overflow-wrap: anywhere; }
    blockquote { margin: 12px 0; padding: 10px 14px; border-left: 3px solid #a9bfca;
      background: #f5f8fa; white-space: pre-wrap; }
    .suggestion { border-top: 1px solid #cbd5df; padding: 18px 0; }
    .update { padding-bottom: 16px; border-bottom: 2px solid #dce5ea; }
    .review-fields { border: 1px solid #cbd5df; background: #f5f8fa;
      border-radius: 6px; padding: 14px; margin-top: 14px; min-width: 0; }
    .review-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .confirmation { display: flex; gap: 8px; align-items: center; margin-top: 14px; }
    .notice { color: #425d6b; }
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
      .review-grid { grid-template-columns: 1fr; }
      .monitoring-counts { grid-template-columns: repeat(2, 1fr); }
    }
  </style>
  <script src="/static/onboarding.js" defer></script>
</head>
<body>
<main>
  <h1>Onboard HQ</h1>
  <p>Provider onboarding dashboard</p>
  <p class="notice"><strong>Prototype:</strong> Use synthetic updates only. Updates,
    suggestions, and review history are saved. Only a manager's approval changes the checklist.</p>
  <section aria-labelledby="role-heading">
    <h2 id="role-heading">Demo role</h2>
    <label for="demo-role">Simulated role</label>
    <select id="demo-role"><option value="proposer">Proposer</option><option value="manager">Manager</option></select>
    <p class="notice">Anyone can propose an update. Manager mode can approve, correct,
      or reject suggestions. This switch simulates a role; it does not verify identity.</p>
  </section>
  <section aria-labelledby="provider-heading">
    <h2 id="provider-heading">1. Select a provider</h2>
    <label for="provider">Provider</label>
    <select id="provider" disabled><option>Loading providers…</option></select>
    <p id="provider-description"></p>
    <button id="refresh-data" type="button">Refresh data</button>
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
          <th scope="col">Monitoring</th></tr></thead>
        <tbody id="requirements"></tbody>
      </table>
    </div>
  </section>
  <section aria-labelledby="update-heading">
    <h2 id="update-heading">3. Propose an update</h2>
    <form id="update-form" action="/updates/analyze" method="post">
      <label for="update-text">Original update</label>
      <textarea id="update-text" required placeholder="Enter a synthetic onboarding update"></textarea>
      <div class="actions"><button class="primary" id="submit-update" type="submit" disabled>Analyze update</button></div>
    </form>
    <p id="request-status" role="status" aria-live="polite">Loading saved data…</p>
  </section>
  <section aria-labelledby="review-heading">
    <h2 id="review-heading">4. Suggestions and review history</h2>
    <div id="review-results"></div>
  </section>
</main>
</body>
</html>
"""
