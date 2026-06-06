(function (window) {
  'use strict';

  function toArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function color(value, fallback) {
    return value || fallback;
  }

  function resolveDatalabelDisplay(display, context) {
    if (typeof display === 'function') {
      return Boolean(display(context));
    }
    return display !== false;
  }

  function SimpleChart(canvas, config) {
    this.canvas = canvas;
    this.ctx = canvas && canvas.getContext ? canvas.getContext('2d') : null;
    this.config = config || {};
    this.draw();
  }

  SimpleChart.register = function () {};

  SimpleChart.prototype.destroy = function () {
    if (!this.ctx || !this.canvas) return;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  };

  SimpleChart.prototype.draw = function () {
    var canvas = this.canvas;
    var ctx = this.ctx;
    if (!canvas || !ctx) return;

    var parent = canvas.parentElement;
    var width = Math.max(parent ? parent.clientWidth : canvas.clientWidth, 320);
    var height = Math.max(parent ? parent.clientHeight : canvas.clientHeight, 220);
    var ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);

    var data = this.config.data || {};
    var labels = toArray(data.labels);
    var datasets = toArray(data.datasets);
    if (!labels.length || !datasets.length) return;

    var allValues = [];
    datasets.forEach(function (dataset) {
      toArray(dataset.data).forEach(function (value) {
        var numberValue = Number(value);
        if (Number.isFinite(numberValue)) allValues.push(numberValue);
      });
    });
    var maxValue = Math.max.apply(Math, allValues.concat([1]));
    var topValue = Math.max(1, Math.ceil(maxValue * 1.2));

    var options = this.config.options || {};
    var scales = options.scales || {};
    var yTicks = (((scales.y || {}).ticks) || {});
    var xTicks = (((scales.x || {}).ticks) || {});
    var gridColor = ((((scales.y || {}).grid) || {}).color) || 'rgba(0,0,0,0.06)';
    var textColor = yTicks.color || xTicks.color || 'rgba(0,0,0,0.5)';
    var chartLeft = 42;
    var chartTop = 20;
    var chartRight = width - 12;
    var chartBottom = height - 38;
    var chartWidth = chartRight - chartLeft;
    var chartHeight = chartBottom - chartTop;

    ctx.save();
    ctx.font = '11px sans-serif';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = textColor;
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;

    var ticks = Math.min(yTicks.maxTicksLimit || 5, 6);
    for (var tick = 0; tick <= ticks; tick += 1) {
      var value = topValue * tick / ticks;
      var y = chartBottom - (value / topValue) * chartHeight;
      ctx.beginPath();
      ctx.moveTo(chartLeft, y);
      ctx.lineTo(chartRight, y);
      ctx.stroke();
      ctx.fillText(String(Math.round(value)), 4, y);
    }

    var slotWidth = chartWidth / labels.length;
    datasets.forEach(function (dataset, datasetIndex) {
      var datasetValues = toArray(dataset.data).map(Number);
      var isLine = dataset.type === 'line';
      var points = [];

      if (isLine) {
        ctx.beginPath();
        datasetValues.forEach(function (value, index) {
          var x = chartLeft + slotWidth * index + slotWidth / 2;
          var y = chartBottom - (Math.max(value, 0) / topValue) * chartHeight;
          points.push({x: x, y: y, value: value, index: index});
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.strokeStyle = color(dataset.borderColor, '#ea580c');
        ctx.lineWidth = dataset.borderWidth || 2;
        ctx.stroke();
        points.forEach(function (point) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, dataset.pointRadius || 3, 0, Math.PI * 2);
          ctx.fillStyle = color(dataset.pointBackgroundColor, dataset.borderColor || '#ea580c');
          ctx.fill();
        });
      } else {
        var barDatasets = datasets.filter(function (item) { return item.type !== 'line'; }).length || 1;
        var barIndex = datasets.slice(0, datasetIndex + 1).filter(function (item) { return item.type !== 'line'; }).length - 1;
        var gap = Math.min(slotWidth * 0.2, 16);
        var barWidth = Math.min((slotWidth - gap) / barDatasets, dataset.maxBarThickness || 48);
        datasetValues.forEach(function (value, index) {
          var x = chartLeft + slotWidth * index + (slotWidth - barWidth * barDatasets) / 2 + barWidth * barIndex;
          var barHeight = (Math.max(value, 0) / topValue) * chartHeight;
          var y = chartBottom - barHeight;
          ctx.fillStyle = color(dataset.backgroundColor, '#4f46e5');
          ctx.fillRect(x, y, barWidth * 0.9, barHeight);
          points.push({x: x + barWidth * 0.45, y: y, value: value, index: index});
        });
      }

      points.forEach(function (point) {
        var datalabels = dataset.datalabels || ((options.plugins || {}).datalabels) || {};
        var context = {dataset: dataset, dataIndex: point.index};
        if (!resolveDatalabelDisplay(datalabels.display, context) || point.value <= 0) return;
        ctx.fillStyle = datalabels.color || textColor;
        ctx.font = ((datalabels.font || {}).weight ? (datalabels.font.weight + ' ') : '') + (((datalabels.font || {}).size) || 10) + 'px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(String(point.value), point.x, Math.max(chartTop + 8, point.y - 8));
      });
    });

    ctx.fillStyle = textColor;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    labels.forEach(function (label, index) {
      var showLabel = true;
      if (typeof xTicks.callback === 'function') {
        showLabel = Boolean(xTicks.callback.call({getLabelForValue: function () { return label; }}, label, index));
      }
      if (!showLabel) return;
      ctx.fillText(String(label), chartLeft + slotWidth * index + slotWidth / 2, chartBottom + 18);
    });

    var legend = (((options.plugins || {}).legend) || {});
    if (legend.display) {
      var legendX = chartLeft;
      datasets.forEach(function (dataset) {
        ctx.fillStyle = color(dataset.borderColor || dataset.backgroundColor, '#4f46e5');
        ctx.fillRect(legendX, 2, 10, 10);
        ctx.fillStyle = textColor;
        ctx.textAlign = 'left';
        ctx.fillText(dataset.label || '', legendX + 14, 8);
        legendX += ctx.measureText(dataset.label || '').width + 44;
      });
    }

    ctx.restore();
  };

  window.Chart = SimpleChart;
  window.ChartDataLabels = {};
})(window);
