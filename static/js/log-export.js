/* Shared helper: builds a branded PDF contact-log from an array of log rows.
   Used by the public "Download Log" modal (index.html) and the admin dashboard
   (admin.html). Requires a backend endpoint that returns JSON like:
     { ok: true, count: N, logs: [ { name, phone, machine, action, created }, ... ] }
   Exposes window.buildLogPdf(logs). */
(function () {
  'use strict';

  function loadJspdf() {
    return new Promise(function (resolve, reject) {
      if (window.jspdf && window.jspdf.jsPDF) return resolve();
      var s = document.createElement('script');
      s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js';
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Failed to load PDF library')); };
      document.head.appendChild(s);
    });
  }

  function logoDataUrl() {
    return new Promise(function (resolve) {
      var img = new Image();
      img.onload = function () {
        try {
          var MAX_W = 260;
          var scale = Math.min(1, MAX_W / img.naturalWidth);
          var w = Math.round(img.naturalWidth * scale);
          var h = Math.round(img.naturalHeight * scale);
          var c = document.createElement('canvas');
          c.width = w;
          c.height = h;
          c.getContext('2d').drawImage(img, 0, 0, w, h);
          resolve(c.toDataURL('image/png'));
        } catch (e) { resolve(null); }
      };
      img.onerror = function () { resolve(null); };
      img.src = '/static/images/logo.png';
    });
  }

  async function buildLogPdf(logs) {
    await loadJspdf();
    var jsPDF = window.jspdf.jsPDF;
    var doc = new jsPDF({ unit: 'pt', format: 'a4' });
    var W = doc.internal.pageSize.getWidth();
    var H = doc.internal.pageSize.getHeight();
    var M = 48;

    var GREEN = [29, 74, 55];
    var GREEN_DARK = [18, 52, 37];
    var BRIGHT = [87, 181, 137];
    var DARK = [21, 25, 23];
    var MUTED = [92, 102, 97];
    var LIGHT = [246, 246, 244];
    var BORDER = [226, 228, 225];
    var WHITE = [255, 255, 255];

    // ---- Header band ----
    doc.setFillColor(GREEN[0], GREEN[1], GREEN[2]);
    doc.rect(0, 0, W, 132, 'F');
    doc.setFillColor(GREEN_DARK[0], GREEN_DARK[1], GREEN_DARK[2]);
    doc.rect(0, 132, W, 6, 'F');

    var logoX = M;
    var logo = await logoDataUrl();
    if (logo) {
      doc.addImage(logo, 'PNG', logoX, 46, 60, 40);
      logoX = M + 60 + 16;
    }
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(22);
    doc.setTextColor(WHITE[0], WHITE[1], WHITE[2]);
    doc.text('GENSPECH INVESTMENTS', logoX, 66);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(BRIGHT[0], BRIGHT[1], BRIGHT[2]);
    doc.text('EQUIPMENT  ·  ENERGY  ·  CONSTRUCTION', logoX, 82);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(16);
    doc.setTextColor(WHITE[0], WHITE[1], WHITE[2]);
    doc.text('CONTACT LOG', W - M, 58, { align: 'right' });
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(BRIGHT[0], BRIGHT[1], BRIGHT[2]);
    doc.text(new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }), W - M, 76, { align: 'right' });

    var colW = W - M * 2;
    var rowH = 26;
    var cols = [
      { label: 'DATE', w: 0.17 },
      { label: 'NAME', w: 0.27 },
      { label: 'PHONE', w: 0.20 },
      { label: 'MACHINE', w: 0.24 },
      { label: 'ACTION', w: 0.12 }
    ];
    var x0 = M;

    function tableHeader(yy) {
      doc.setFillColor(GREEN[0], GREEN[1], GREEN[2]);
      doc.rect(x0, yy, colW, rowH, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor(WHITE[0], WHITE[1], WHITE[2]);
      var cx = x0;
      for (var i = 0; i < cols.length; i++) {
        doc.text(cols[i].label, cx + 10, yy + 17);
        cx += colW * cols[i].w;
      }
      return yy + rowH;
    }

    var y = 176;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(GREEN[0], GREEN[1], GREEN[2]);
    doc.text('NAMES & PHONE NUMBERS CAPTURED', M, y);
    y += 22;
    y = tableHeader(y);

    doc.setLineWidth(1);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    for (var i = 0; i < logs.length; i++) {
      var r = logs[i];
      if (y > H - 90) {
        doc.addPage();
        y = 56;
        y = tableHeader(y);
        doc.setLineWidth(1);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(9);
      }
      if (i % 2 === 0) {
        doc.setFillColor(LIGHT[0], LIGHT[1], LIGHT[2]);
        doc.rect(x0, y, colW, rowH, 'F');
      }
      doc.setDrawColor(BORDER[0], BORDER[1], BORDER[2]);
      doc.line(x0, y + rowH, x0 + colW, y + rowH);
      doc.setTextColor(DARK[0], DARK[1], DARK[2]);
      var vals = [r.created || '', r.name || '-', r.phone || '-', r.machine || '-', r.action || ''];
      var cx = x0;
      for (var ci = 0; ci < cols.length; ci++) {
        doc.text(String(vals[ci]).slice(0, 30), cx + 10, y + 17);
        cx += colW * cols[ci].w;
      }
      y += rowH;
    }

    // ---- Footer on every page ----
    var pageCount = doc.internal.getNumberOfPages();
    for (var p = 1; p <= pageCount; p++) {
      doc.setPage(p);
      doc.setDrawColor(BRIGHT[0], BRIGHT[1], BRIGHT[2]);
      doc.setLineWidth(2);
      doc.line(M, H - 80, W - M, H - 80);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
      doc.text('ZIMRA Registered & Compliant  ·  Genspech Investments  ·  0783 044 407 / 0718 029 974', M, H - 60);
      doc.text('Page ' + p + ' of ' + pageCount, W - M, H - 60, { align: 'right' });
    }

    doc.save('Genspech_Contact_Log.pdf');
  }

  window.buildLogPdf = buildLogPdf;
})();
