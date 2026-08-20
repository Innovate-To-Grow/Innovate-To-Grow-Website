(function () {
  'use strict';

  const root = document.getElementById('infrastructure-status-root');
  if (!root) return;

  const banner = document.getElementById('infrastructure-status-banner');
  const updated = document.getElementById('infrastructure-status-updated');
  const overview = document.getElementById('infrastructure-status-overview');
  const services = document.getElementById('infrastructure-status-services');
  const probes = document.getElementById('infrastructure-status-probes');
  const alarms = document.getElementById('infrastructure-status-alarms');
  const resources = document.getElementById('infrastructure-status-resources');
  const errorsPanel = document.getElementById('infrastructure-status-errors-panel');
  const errors = document.getElementById('infrastructure-status-errors');
  const refresh = document.getElementById('infrastructure-status-refresh');
  const dataUrl = root.getAttribute('data-status-url');
  let requestInFlight = false;

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) node.textContent = String(value);
    return node;
  }

  function valueOrDash(value) {
    return value === undefined || value === null || value === '' ? '—' : String(value);
  }

  function count(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toLocaleString() : '—';
  }

  function dateTime(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? valueOrDash(value) : parsed.toLocaleString();
  }

  function statusKind(value) {
    const normalized = String(value || '').toLowerCase();
    if (['operational', 'ok', 'active', 'available', 'succeed', 'success', 'successful', 'healthy'].includes(normalized) || normalized.endsWith('_complete')) {
      return 'good';
    }
    if (['degraded', 'partial', 'insufficient_data', 'initial', 'draining', 'in_progress'].includes(normalized)) {
      return 'warning';
    }
    if (['major_outage', 'alarm', 'failed', 'unhealthy', 'inactive'].includes(normalized) || normalized.endsWith('_failed') || normalized.includes('rollback')) {
      return 'bad';
    }
    return 'unknown';
  }

  function badge(value) {
    const label = valueOrDash(value).replaceAll('_', ' ');
    return element('span', 'i2g-status-badge i2g-status-badge--' + statusKind(value), label);
  }

  function badgeCell(value) {
    const cell = element('td');
    cell.append(badge(value));
    return cell;
  }

  function addDetail(list, label, value) {
    list.append(element('dt', '', label), element('dd', '', valueOrDash(value)));
  }

  function card(label, value, detail, state) {
    const node = element('article', 'i2g-status-card');
    const heading = element('div', 'i2g-status-card-heading');
    heading.append(element('span', 'i2g-status-card-label', label));
    if (state) heading.append(badge(state));
    node.append(heading, element('div', 'i2g-status-card-value', valueOrDash(value)));
    if (detail) node.append(element('div', 'i2g-status-card-detail', detail));
    return node;
  }

  function renderBanner(envelope) {
    banner.hidden = true;
    banner.className = 'i2g-status-banner';
    banner.replaceChildren();
    if (!envelope.available) {
      banner.textContent = envelope.message || 'Infrastructure status is unavailable.';
      banner.classList.add('i2g-status-banner--error');
      banner.hidden = false;
    } else if (envelope.stale) {
      banner.textContent = (envelope.message || 'Live refresh failed.') + ' Showing the most recent successful snapshot.';
      banner.classList.add('i2g-status-banner--warning');
      banner.hidden = false;
    } else if (envelope.status && envelope.status.partial) {
      banner.textContent = 'Some AWS sources could not be read. Available infrastructure details are shown below.';
      banner.classList.add('i2g-status-banner--warning');
      banner.hidden = false;
    }
  }

  function renderOverview(envelope) {
    overview.replaceChildren();
    const data = envelope.status || {};
    const stack = data.stack || {};
    const serviceRows = Array.isArray(data.services) ? data.services : [];
    const alarmRows = Array.isArray(data.alarms) ? data.alarms : [];
    const activeAlarms = alarmRows.filter(function (item) { return String(item.state || '').toUpperCase() === 'ALARM'; }).length;
    const healthyServices = serviceRows.filter(function (item) { return statusKind(item.summaryStatus) === 'good'; }).length;

    const stackDetail = [stack.region, stack.accountId, stack.version ? 'version ' + stack.version : ''].filter(Boolean).join(' · ');
    overview.append(
      card('Stack', stack.name, stackDetail, stack.stackStatus),
      card('Snapshot', dateTime(data.generatedAt), envelope.stale ? 'Cached snapshot' : 'Live internal API', envelope.stale ? 'degraded' : 'operational'),
      card('Services', healthyServices + ' / ' + serviceRows.length, 'Operational services', healthyServices === serviceRows.length && serviceRows.length ? 'operational' : 'degraded'),
      card('Alarms', activeAlarms, alarmRows.length + ' configured alarms', activeAlarms ? 'alarm' : 'ok')
    );
    updated.textContent = envelope.fetchedAt ? 'Backend fetched ' + dateTime(envelope.fetchedAt) : '';
  }

  function renderServices(data) {
    services.replaceChildren();
    const rows = Array.isArray(data.services) ? data.services : [];
    if (!rows.length) {
      services.append(element('p', 'i2g-status-muted', 'No service details are available.'));
      return;
    }
    rows.forEach(function (service) {
      const node = element('article', 'i2g-status-service');
      const heading = element('div', 'i2g-status-service-heading');
      heading.append(element('h4', '', service.name || service.id || 'Service'), badge(service.summaryStatus));
      const details = element('dl', 'i2g-status-details');
      addDetail(details, 'Environment', service.environment);
      addDetail(details, 'Public component', service.publicComponentId);

      const aws = service.aws || {};
      if (aws.amplify) {
        const job = aws.amplify.lastJob || {};
        addDetail(details, 'Platform', 'AWS Amplify');
        addDetail(details, 'App / branch', [aws.amplify.appId, aws.amplify.branch].filter(Boolean).join(' / '));
        addDetail(details, 'Last job', [job.status, job.commitId].filter(Boolean).join(' · '));
        addDetail(details, 'Job completed', job.endedAt ? dateTime(job.endedAt) : dateTime(job.startedAt));
      }
      if (aws.ecs) {
        const deployments = Array.isArray(aws.ecs.deployments) ? aws.ecs.deployments : [];
        const latestDeployment = deployments[0] || {};
        addDetail(details, 'Platform', 'Amazon ECS');
        addDetail(details, 'Cluster / service', [aws.ecs.cluster, aws.ecs.service].filter(Boolean).join(' / '));
        addDetail(details, 'Tasks', count(aws.ecs.running) + ' running · ' + count(aws.ecs.desired) + ' desired · ' + count(aws.ecs.pending) + ' pending');
        addDetail(details, 'Task definition', aws.ecs.taskDefinition);
        if (deployments.length) addDetail(details, 'Deployment', latestDeployment.rolloutState || latestDeployment.status);
      }
      if (aws.loadBalancer) {
        const targetHealth = Array.isArray(aws.loadBalancer.targetHealth) ? aws.loadBalancer.targetHealth : [];
        const healthyTargets = targetHealth.filter(function (target) { return target.state === 'healthy'; }).length;
        addDetail(details, 'Load balancer', aws.loadBalancer.name || aws.loadBalancer.dnsName);
        addDetail(details, 'Target health', healthyTargets + ' / ' + targetHealth.length + ' healthy');
      }
      const dependencies = Array.isArray(aws.dependencies) ? aws.dependencies : [];
      if (dependencies.length) {
        const ready = dependencies.filter(function (dependency) { return statusKind(dependency.status) === 'good'; }).length;
        addDetail(details, 'Dependencies', ready + ' / ' + dependencies.length + ' ready');
        dependencies.forEach(function (dependency) {
          const label = valueOrDash(dependency.type).replaceAll('_', ' ');
          addDetail(details, 'Dependency · ' + label, valueOrDash(dependency.status).replaceAll('_', ' '));
        });
      }
      node.append(heading, details);
      services.append(node);
    });
  }

  function emptyTable(body, columns, message) {
    const row = element('tr');
    const cell = element('td', 'i2g-status-empty', message);
    cell.colSpan = columns;
    row.append(cell);
    body.append(row);
  }

  function renderProbes(data) {
    probes.replaceChildren();
    const rows = Array.isArray(data.probes) ? data.probes : [];
    if (!rows.length) {
      emptyTable(probes, 5, 'No probe results are available.');
      return;
    }
    rows.forEach(function (probe) {
      const last = probe.last || {};
      const row = element('tr');
      row.append(
        element('td', '', probe.componentId),
        badgeCell(last.outcome),
        element('td', '', valueOrDash(last.httpStatus)),
        element('td', '', last.latencyMs === undefined || last.latencyMs === null ? '—' : count(last.latencyMs) + ' ms'),
        element('td', '', dateTime(last.checkedAt))
      );
      probes.append(row);
    });
  }

  function renderAlarms(data) {
    alarms.replaceChildren();
    const rows = Array.isArray(data.alarms) ? data.alarms : [];
    if (!rows.length) {
      emptyTable(alarms, 5, 'No alarm details are available.');
      return;
    }
    rows.forEach(function (alarm) {
      const row = element('tr');
      row.append(
        element('td', '', alarm.name),
        badgeCell(alarm.state),
        element('td', '', [alarm.namespace, alarm.metric].filter(Boolean).join(' / ')),
        element('td', '', dateTime(alarm.updatedAt)),
        element('td', '', alarm.reason)
      );
      alarms.append(row);
    });
  }

  function renderResources(data) {
    resources.replaceChildren();
    const stack = data.stack && typeof data.stack === 'object' ? data.stack : {};
    const rows = Array.isArray(stack.resources) ? stack.resources : [];
    if (!rows.length) {
      emptyTable(resources, 4, 'No stack resource details are available.');
      return;
    }
    rows.forEach(function (resource) {
      const row = element('tr');
      row.append(
        element('td', '', resource.logicalId),
        element('td', '', resource.type),
        element('td', '', resource.physicalId),
        badgeCell(resource.status)
      );
      resources.append(row);
    });
  }

  function renderErrors(data) {
    errors.replaceChildren();
    const rows = Array.isArray(data.errors) ? data.errors : [];
    errorsPanel.hidden = !rows.length;
    rows.forEach(function (item) {
      const prefix = [item.source, item.code].filter(Boolean).join(' · ');
      const message = [prefix, item.message, item.at ? dateTime(item.at) : ''].filter(Boolean).join(' — ');
      errors.append(element('li', '', message));
    });
  }

  function render(envelope) {
    const safeEnvelope = envelope && typeof envelope === 'object' ? envelope : { available: false };
    const data = safeEnvelope.status && typeof safeEnvelope.status === 'object' ? safeEnvelope.status : {};
    renderBanner(safeEnvelope);
    renderOverview(safeEnvelope);
    renderServices(data);
    renderProbes(data);
    renderAlarms(data);
    renderResources(data);
    renderErrors(data);
  }

  async function refreshData() {
    if (requestInFlight) return;
    requestInFlight = true;
    refresh.disabled = true;
    refresh.setAttribute('aria-busy', 'true');
    try {
      const separator = dataUrl.includes('?') ? '&' : '?';
      const response = await fetch(dataUrl + separator + 'force=1', {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error('Request failed');
      render(await response.json());
    } catch (error) {
      banner.textContent = 'The status refresh failed. Existing details remain on screen.';
      banner.className = 'i2g-status-banner i2g-status-banner--error';
      banner.hidden = false;
    } finally {
      requestInFlight = false;
      refresh.disabled = false;
      refresh.removeAttribute('aria-busy');
    }
  }

  const initialNode = document.getElementById('infrastructure-status-initial-data');
  try {
    render(JSON.parse(initialNode ? initialNode.textContent : '{}'));
  } catch (error) {
    render({ available: false, message: 'Infrastructure status could not be displayed.' });
  }

  refresh.addEventListener('click', refreshData);
}());
