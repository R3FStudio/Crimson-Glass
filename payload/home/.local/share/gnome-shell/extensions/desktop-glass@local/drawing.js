import Cairo from 'cairo';

const TAU = 2 * Math.PI;
const WHITE = [0.99, 0.96, 0.97];
const RED = [1, 0.27, 0.34];
const MUTED = [0.90, 0.78, 0.81];
const DIGITS = {
    '0': ['01110', '11011', '11011', '11011', '11011', '11011', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00110', '01000', '10000', '11111'],
    '3': ['11110', '00001', '00001', '01110', '00001', '00001', '11110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '10000', '11110', '00001', '00001', '11110'],
    '6': ['01110', '10000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    '8': ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    '9': ['01110', '10001', '10001', '01111', '00001', '00001', '01110'],
    ':': ['0', '0', '1', '0', '1', '0', '0'],
};

function fill(cr, color, alpha = 1) {
    cr.setSourceRGBA(...color, alpha);
    cr.fill();
}

function dot(cr, x, y, radius, color, alpha = 1) {
    cr.newSubPath();
    cr.arc(x, y, radius, 0, TAU);
    fill(cr, color, alpha);
}

function rounded(cr, x, y, w, h, r) {
    cr.newSubPath();
    cr.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
    cr.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
    cr.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
    cr.arc(x + r, y + r, r, Math.PI, 1.5 * Math.PI);
    cr.closePath();
}

function line(cr, x1, y1, x2, y2, width, color, alpha = 1) {
    cr.moveTo(x1, y1);
    cr.lineTo(x2, y2);
    cr.setLineCap(Cairo.LineCap.ROUND);
    cr.setLineWidth(width);
    cr.setSourceRGBA(...color, alpha);
    cr.stroke();
}

function label(cr, str, x, y, opts = {}) {
    const {size = 12, mono = false, bold = false, color = WHITE, alpha = 1,
        align = 'left', maxWidth = Infinity} = opts;
    cr.selectFontFace(mono ? 'DejaVu Sans Mono' : 'Sans', Cairo.FontSlant.NORMAL,
        bold ? Cairo.FontWeight.BOLD : Cairo.FontWeight.NORMAL);
    cr.setFontSize(size);
    let text = str;
    if (cr.textExtents(text).width > maxWidth) {
        while (text && cr.textExtents(`${text}…`).width > maxWidth)
            text = text.slice(0, -1);
        text += '…';
    }
    const ext = cr.textExtents(text);
    const offset = align === 'center' ? ext.width / 2 : align === 'right' ? ext.width : 0;
    cr.moveTo(x - offset - ext.xBearing, y);
    cr.setSourceRGBA(...color, alpha);
    cr.showText(text);
}

function matrixTime(cr, time, center, top) {
    const spacing = 4.1;
    const glyphs = [...time].map(ch => DIGITS[ch]).filter(Boolean);
    const width = glyphs.reduce((sum, rows) => sum + rows[0].length + 1, -1);
    let x = center - width * spacing / 2;
    glyphs.forEach(rows => {
        rows.forEach((row, i) => [...row].forEach((on, j) => {
            if (on === '1')
                dot(cr, x + j * spacing, top + i * spacing, 1.30, WHITE, 0.98);
        }));
        x += (rows[0].length + 1) * spacing;
    });
}

export function surface(cr, w, h, r, hasBlur, opacity) {
    rounded(cr, 0.9, 0.9, w - 1.8, h - 1.8, r - 0.9);
    const tint = new Cairo.LinearGradient(0, 0, w * 0.55, h);
    tint.addColorStopRGBA(0, 0.105, 0.085, 0.10, hasBlur ? opacity : 0.79);
    tint.addColorStopRGBA(0.48, 0.035, 0.035, 0.047, hasBlur ? opacity : 0.86);
    tint.addColorStopRGBA(1, 0.024, 0.023, 0.035, hasBlur ? opacity : 0.91);
    cr.setSource(tint);
    cr.fillPreserve();

    const rim = new Cairo.LinearGradient(0, 0, w * 0.68, h);
    rim.addColorStopRGBA(0, 1, 0.78, 0.83, 0.69);
    rim.addColorStopRGBA(0.24, 1, 0.42, 0.50, 0.48);
    rim.addColorStopRGBA(0.63, 0.84, 0.13, 0.26, 0.28);
    rim.addColorStopRGBA(1, 1, 0.24, 0.38, 0.72);
    cr.setSource(rim);
    cr.setLineWidth(1.4);
    cr.stroke();

    rounded(cr, 3.2, 3.2, w - 6.4, h - 6.4, r - 3.2);
    const innerRim = new Cairo.LinearGradient(0, 0, w * 0.3, h * 0.58);
    innerRim.addColorStopRGBA(0, 1, 0.95, 0.97, 0.26);
    innerRim.addColorStopRGBA(1, 1, 0.95, 0.97, 0);
    cr.setSource(innerRim);
    cr.setLineWidth(0.7);
    cr.stroke();
}

export function clock(cr, now, twelveHour) {
    const x = 114;
    const y = 96;
    const hour = now.get_hour();
    const minute = now.get_minute();
    const seconds = now.get_second();

    cr.arc(x, y, 64, 0, TAU);
    fill(cr, [0.02, 0.01, 0.025], 0.10);
    for (let i = 0; i < 60; i++) {
        const angle = i * TAU / 60 - Math.PI / 2;
        const marked = i % 5 === 0;
        const cardinal = i % 15 === 0;
        dot(cr, x + Math.cos(angle) * 56, y + Math.sin(angle) * 56,
            cardinal ? 2.45 : marked ? 1.75 : 0.8,
            i === 0 ? RED : WHITE, marked ? 0.86 : 0.27);
    }

    const hourAngle = (hour % 12 + minute / 60) * TAU / 12 - Math.PI / 2;
    const minuteAngle = (minute + seconds / 60) * TAU / 60 - Math.PI / 2;
    line(cr, x, y, x + Math.cos(hourAngle) * 27, y + Math.sin(hourAngle) * 27, 7, WHITE, 0.99);
    line(cr, x, y, x + Math.cos(minuteAngle) * 44, y + Math.sin(minuteAngle) * 44, 3.4, WHITE, 0.77);
    const secAngle = seconds * TAU / 60 - Math.PI / 2;
    dot(cr, x + Math.cos(secAngle) * 56, y + Math.sin(secAngle) * 56, 2.6, RED);
    dot(cr, x, y, 4, WHITE);

    const time = twelveHour ? now.format('%l:%M').trim() : now.format('%H:%M');
    matrixTime(cr, time, x, 165);
    label(cr, now.format('%a  %b %e').replace(/ +/g, ' ').toLocaleUpperCase(), x, 209,
        {size: 10.5, mono: true, bold: true, align: 'center', color: MUTED});
}

export function system(cr, stats) {
    label(cr, 'SYSTEM', 22, 29, {size: 14, mono: true, bold: true});
    dot(cr, 277, 24, 2.65, RED);
    label(cr, 'LIVE', 308, 28, {size: 10, mono: true, align: 'right', color: MUTED});

    ['CPU', 'RAM', 'GPU'].forEach((name, i) => {
        const x = 22 + i * 99;
        const value = stats.metrics[i];
        label(cr, name, x, 55, {size: 9.5, mono: true, bold: true, color: MUTED});
        label(cr, value === null ? '—' : `${value}%`, x + 85, 55,
            {size: 11.5, mono: true, bold: true, align: 'right'});
        for (let tick = 0; tick < 15; tick++) {
            const active = value !== null && tick < Math.ceil(value * 15 / 100);
            const bright = tick >= 11;
            dot(cr, x + 2.2 + tick * 5.65, 67, 1.65, active && bright ? RED : WHITE,
                active ? 0.9 : 0.18);
        }
    });

    line(cr, 22, 85, 308, 85, 0.75, WHITE, 0.21);
    const specs = [
        ['CPU', stats.cpu],
        ['GPU', [stats.gpu, stats.vram].filter(Boolean).join('  ·  ')],
        ['RAM', stats.memory],
        ['SSD', stats.storage],
        ['OS', stats.os],
    ];
    specs.forEach(([name, value], i) => {
        const y = 107 + i * 23;
        label(cr, name, 22, y, {size: 9.5, mono: true, bold: true, color: MUTED, alpha: 0.82});
        label(cr, value, 73, y, {size: 12.5, bold: i <= 1, maxWidth: 230});
    });
}

export function resizeGrip(cr, x, y) {
    line(cr, x - 10, y, x, y - 10, 1.5, WHITE, 0.7);
    line(cr, x - 5, y, x, y - 5, 1.5, WHITE, 0.7);
}
