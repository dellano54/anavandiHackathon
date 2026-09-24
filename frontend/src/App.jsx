import { useState, useEffect } from 'react';
import { 
  Waves, Calendar as CalendarIcon, Map as MapIcon, Info,
  Cloud, Droplet, AlertTriangle, ArrowUp, Leaf, HelpCircle, MapPin,
  Home, BarChart2, Play, Pause
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';

const RealImageMap = ({ type, isChangeMap }) => {
    // type is 'dec', 'jan', 'mar', 'jun', or 'change'
    return (
      <div className="absolute inset-0 bg-[#1e293b] overflow-hidden">
          
          {/* Base images stacked for crossfade morphing */}
          {(!isChangeMap || type !== 'change') && (
            <>
              {/* Dec 2025 -> map-jan.png */}
              <img src="/map-jan.png" className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-1000 ${type === 'dec' ? 'opacity-100' : 'opacity-0'}`} />
              
              {/* Jan 2026 -> map-mar.png */}
              <img src="/map-mar.png" className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-1000 ${type === 'jan' ? 'opacity-100' : 'opacity-0'}`} />
              
              {/* Mar 2026 -> map-jun.png */}
              <img src="/map-jun.png" className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-1000 ${type === 'mar' ? 'opacity-100' : 'opacity-0'}`} />
              
              {/* Jun 2026 -> map-jan.png with cloudy overlay */}
              <div className={`absolute inset-0 w-full h-full transition-opacity duration-1000 ${type === 'jun' ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
                  <img src="/map-jan.png" className="absolute inset-0 w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-white/60 backdrop-blur-[2px]"></div>
                  <svg className="absolute inset-0 w-full h-full" xmlns="http://www.w3.org/2000/svg">
                     <filter id="blur"><feGaussianBlur stdDeviation="8" /></filter>
                     <circle cx="20%" cy="30%" r="20%" fill="white" opacity="0.8" filter="url(#blur)" />
                     <circle cx="80%" cy="40%" r="25%" fill="white" opacity="0.9" filter="url(#blur)" />
                     <circle cx="40%" cy="70%" r="30%" fill="white" opacity="0.7" filter="url(#blur)" />
                     <circle cx="70%" cy="80%" r="20%" fill="white" opacity="0.8" filter="url(#blur)" />
                  </svg>
              </div>
            </>
          )}

          {/* Change Map specific visuals (if no specific 4th image is provided) */}
          {isChangeMap && type === 'change' && (
            <>
              {/* Fallback to June image as base, with heavy filtering, or just use June */}
              <img src="/map-jun.png" className="absolute inset-0 w-full h-full object-cover opacity-100" />
              <div className="absolute inset-0 bg-red-500/10 mix-blend-color"></div>
              <svg className="w-full h-full absolute inset-0 pointer-events-none drop-shadow-md" viewBox="0 0 100 100" preserveAspectRatio="none">
                 <ellipse cx="50" cy="55" rx="15" ry="10" fill="none" stroke="#ef4444" strokeWidth="1" strokeDasharray="2 2" />
                 <ellipse cx="20" cy="35" rx="12" ry="8" fill="none" stroke="#ef4444" strokeWidth="1" strokeDasharray="2 2" />
              </svg>
            </>
          )}
  
          {/* Map Labels for Large Map */}
          {!isChangeMap && (
              <div className="absolute inset-0 pointer-events-none">
                  {/* Ernakulam */}
                  <div className="absolute top-1/4 left-1/4 bg-[#1e3a8a]/80 text-white text-[10px] px-2 py-0.5 rounded border border-white/20 shadow-sm backdrop-blur-sm">Ernakulam</div>
                  {/* Vembanad Backwater */}
                  <div className="absolute top-1/3 left-4 bg-[#1e3a8a]/80 text-white text-[10px] px-2 py-1 rounded border border-white/20 shadow-sm backdrop-blur-sm flex items-center gap-1"><span className="text-[14px] leading-none">&larr;</span> <div>Vembanad<br/>Backwater</div></div>
                  {/* Alappuzha */}
                  <div className="absolute bottom-6 left-4 bg-[#111827]/80 text-white text-[10px] px-2 py-0.5 rounded shadow-sm flex items-center gap-1 border border-white/20"><span className="text-[14px] leading-none">&larr;</span> Alappuzha</div>
              </div>
          )}
          
          {/* Change Map specific labels */}
          {isChangeMap && (
              <div className="absolute inset-0 pointer-events-none">
                  <div className="absolute top-4 left-6 bg-[#1e3a8a]/80 text-white text-[9px] px-1.5 py-0.5 rounded shadow-sm">Ernakulam</div>
                  <div className="absolute bottom-6 left-2 bg-[#111827]/80 text-white text-[9px] px-1.5 py-0.5 rounded shadow-sm flex items-center gap-1"><span className="text-[12px] leading-none">&larr;</span> Alappuzha</div>
              </div>
          )}
      </div>
    );
}

import { toPng } from 'html-to-image';
import { jsPDF } from 'jspdf';

export default function App() {
  const [activeTab, setActiveTab] = useState('Home');
  const [trendTab, setTrendTab] = useState('All');
  
  // Animation state
  const [currentIndex, setCurrentIndex] = useState(3); // Start at June
  const [isPlaying, setIsPlaying] = useState(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);

  const monthData = [
    {
      id: 'dec',
      label: 'Dec 2025',
      turbidity: 0.18,
      chlorophyll: 0.12,
      suspendedSediments: 0.10,
      cloudCoverage: 2,
      validPixels: 98,
      pollutedPercent: 8,
      isCloudy: false,
    },
    {
      id: 'jan',
      label: 'Jan 2026',
      turbidity: 0.20,
      chlorophyll: 0.15,
      suspendedSediments: 0.12,
      cloudCoverage: 5,
      validPixels: 95,
      pollutedPercent: 10,
      isCloudy: false,
    },
    {
      id: 'mar',
      label: 'Mar 2026',
      turbidity: 0.27,
      chlorophyll: 0.22,
      suspendedSediments: 0.25,
      cloudCoverage: 12,
      validPixels: 88,
      pollutedPercent: 20,
      isCloudy: false,
    },
    {
      id: 'jun',
      label: 'Jun 2026',
      turbidity: null,
      chlorophyll: null,
      suspendedSediments: null,
      cloudCoverage: 85,
      validPixels: 15,
      pollutedPercent: null,
      isCloudy: true,
    }
  ];

  const dates = monthData.map(d => d.id);
  const dateLabels = monthData.map(d => d.label);

  useEffect(() => {
    let interval;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentIndex((prev) => (prev + 1) % dates.length);
      }, 1500); // Change map every 1.5 seconds
    }
    return () => clearInterval(interval);
  }, [isPlaying, dates.length]);

  const currentType = dates[currentIndex];
  const currentData = monthData[currentIndex];

  const chartData = monthData.map((d, idx) => ({
    name: d.label,
    turbidity: idx <= currentIndex ? d.turbidity : null,
    chlorophyll: idx <= currentIndex ? d.chlorophyll : null,
    suspendedSediments: idx <= currentIndex ? d.suspendedSediments : null,
  }));

  const generatePDF = async () => {
    setIsGeneratingPdf(true);
    
    try {
        const pdf = new jsPDF('p', 'mm', 'a4');
        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = pdf.internal.pageSize.getHeight();
        const margin = 15;
        const contentWidth = pdfWidth - margin * 2;

        const addFooter = () => {
            pdf.setFontSize(8);
            pdf.setTextColor(148, 163, 184);
            pdf.setFont("helvetica", "italic");
            pdf.text(
                "Satellite-derived indices are proxies, not laboratory measurements.",
                margin,
                pdfHeight - 10
            );
            pdf.text(
                `Generated ${new Date().toLocaleString()}`,
                pdfWidth - margin,
                pdfHeight - 10,
                { align: 'right' }
            );
        };

        // ---------- 1. HEADER ----------
        pdf.setFillColor(30, 58, 138); // #1e3a8a
        pdf.rect(0, 0, pdfWidth, 38, 'F');

        pdf.setTextColor(255, 255, 255);
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(20);
        pdf.text("Water Quality Analysis", margin, 16);

        pdf.setFontSize(11);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(191, 219, 254); // light blue
        pdf.text("Periyar River Backwater  •  Satellite-Based Detection", margin, 24);

        pdf.setFontSize(9);
        pdf.setTextColor(219, 234, 254);
        pdf.text(
            `Location: Ernakulam, Kerala (10.02N, 76.31E)   |   Date: ${currentData.label}   |   View: Water Quality Map`,
            margin,
            31
        );

        let currentY = 46;

        const ensureSpace = (needed) => {
            if (currentY + needed > pdfHeight - 15) {
                addFooter();
                pdf.addPage();
                currentY = 20;
            }
        };

        // ---------- 2. MAP IMAGE ----------
        pdf.setFontSize(14);
        pdf.setTextColor(30, 58, 138);
        pdf.setFont("helvetica", "bold");
        pdf.text(`Satellite Map — ${currentData.label}`, margin, currentY);
        currentY += 4;

        const mapEl = document.getElementById('map-capture');
        if (mapEl) {
            try {
                const mapImg = await toPng(mapEl, {
                    cacheBust: true,
                    backgroundColor: '#1e293b',
                    pixelRatio: 2
                });
                const ratio = mapEl.offsetWidth / mapEl.offsetHeight;
                let imgW = contentWidth;
                let imgH = imgW / ratio;
                // cap height so data still fits on page 1
                if (imgH > 85) {
                    imgH = 85;
                    imgW = imgH * ratio;
                }
                ensureSpace(imgH + 8);
                // centered, with thin border
                const imgX = margin + (contentWidth - imgW) / 2;
                pdf.setDrawColor(203, 213, 225);
                pdf.setFillColor(255, 255, 255);
                pdf.roundedRect(margin - 2, currentY - 2, contentWidth + 4, imgH + 4, 2, 2, 'FD');
                pdf.addImage(mapImg, 'PNG', imgX, currentY, imgW, imgH);
                currentY += imgH + 10;
            } catch (e) {
                console.warn("Map capture failed", e);
                pdf.setFontSize(10);
                pdf.setTextColor(220, 38, 38);
                pdf.text("[Map image could not be captured]", margin, currentY);
                currentY += 8;
            }
        }

        // ---------- 3. DATA TABLE ----------
        ensureSpace(70);
        pdf.setFontSize(14);
        pdf.setTextColor(30, 58, 138);
        pdf.setFont("helvetica", "bold");
        pdf.text("Data Summary", margin, currentY);
        currentY += 6;

        const rows = [
            ["Cloud Coverage", `${currentData.cloudCoverage}%${currentData.isCloudy ? " (limits analysis)" : ""}`],
            ["Valid Water Pixels", `${currentData.validPixels}%`],
            ["Polluted Area", currentData.pollutedPercent !== null ? `${currentData.pollutedPercent}%` : 'N/A'],
            ["Turbidity Index", currentData.turbidity !== null ? `${currentData.turbidity.toFixed(2)}  (higher = murkier)` : 'N/A'],
            ["Chlorophyll Index", currentData.chlorophyll !== null ? `${currentData.chlorophyll.toFixed(2)}  (higher = more algae)` : 'N/A'],
            ["Suspended Sediments", currentData.suspendedSediments !== null ? `${currentData.suspendedSediments.toFixed(2)}  (higher = more sediment)` : 'N/A'],
        ];

        const rowH = 8;
        const col1W = 60;
        const col2W = contentWidth - col1W;

        // table header
        pdf.setFillColor(30, 58, 138);
        pdf.setTextColor(255, 255, 255);
        pdf.setFontSize(10);
        pdf.setFont("helvetica", "bold");
        pdf.rect(margin, currentY, col1W, rowH, 'F');
        pdf.rect(margin + col1W, currentY, col2W, rowH, 'F');
        pdf.text("Parameter", margin + 3, currentY + 5.5);
        pdf.text("Value", margin + col1W + 3, currentY + 5.5);
        currentY += rowH;

        pdf.setFont("helvetica", "normal");
        rows.forEach(([k, v], i) => {
            ensureSpace(rowH + 2);
            if (i % 2 === 0) pdf.setFillColor(239, 246, 255); // #eff6ff
            else pdf.setFillColor(255, 255, 255);
            pdf.rect(margin, currentY, col1W, rowH, 'F');
            pdf.rect(margin + col1W, currentY, col2W, rowH, 'F');
            pdf.setDrawColor(226, 232, 240);
            pdf.rect(margin, currentY, col1W, rowH, 'D');
            pdf.rect(margin + col1W, currentY, col2W, rowH, 'D');

            pdf.setTextColor(30, 58, 138);
            pdf.setFont("helvetica", "bold");
            pdf.text(k, margin + 3, currentY + 5.5);
            pdf.setTextColor(15, 23, 42);
            pdf.setFont("helvetica", "normal");
            // red for cloudy / N/A polluted
            if (v === 'N/A') pdf.setTextColor(220, 38, 38);
            pdf.text(String(v), margin + col1W + 3, currentY + 5.5);
            currentY += rowH;
        });
        currentY += 6;

        if (currentData.isCloudy) {
            ensureSpace(12);
            pdf.setFillColor(255, 251, 235);
            pdf.setDrawColor(253, 224, 71);
            pdf.roundedRect(margin, currentY, contentWidth, 12, 2, 2, 'FD');
            pdf.setTextColor(161, 98, 7);
            pdf.setFontSize(9);
            pdf.setFont("helvetica", "bold");
            pdf.text("Note: Cloudy - not enough information to come to conclusion.", margin + 4, currentY + 7);
            currentY += 18;
        }

        // ---------- 4. TREND CHART (drawn natively - always visible) ----------
        {
            const chartH = 62;
            ensureSpace(chartH + 16);
            pdf.setFontSize(14);
            pdf.setTextColor(30, 58, 138);
            pdf.setFont("helvetica", "bold");
            pdf.text("Index Trends (average over water body)", margin, currentY);
            currentY += 3;

            // legend
            pdf.setFontSize(8);
            const seriesDefs = [];
            if (trendTab === 'All' || trendTab === 'Turbidity')
                seriesDefs.push({ key: 'turbidity', label: 'Turbidity', rgb: [59, 130, 246] });
            if (trendTab === 'All' || trendTab === 'Chlorophyll')
                seriesDefs.push({ key: 'chlorophyll', label: 'Chlorophyll', rgb: [34, 197, 94] });
            if (trendTab === 'All' || trendTab === 'Suspended Sediments')
                seriesDefs.push({ key: 'suspendedSediments', label: 'Sediments', rgb: [217, 119, 6] });

            let lx = margin;
            pdf.setFont("helvetica", "bold");
            seriesDefs.forEach(s => {
                pdf.setFillColor(s.rgb[0], s.rgb[1], s.rgb[2]);
                pdf.circle(lx + 2, currentY + 2.5, 1.5, 'F');
                pdf.setTextColor(30, 58, 138);
                pdf.text(s.label, lx + 5, currentY + 4);
                lx += pdf.getTextWidth(s.label) + 12;
            });
            currentY += 7;

            // chart box
            const boxX = margin;
            const boxY = currentY;
            const boxW = contentWidth;
            const boxH = chartH;
            pdf.setDrawColor(203, 213, 225);
            pdf.setFillColor(255, 255, 255);
            pdf.roundedRect(boxX - 2, boxY - 2, boxW + 4, boxH + 4, 2, 2, 'FD');

            const padL = 14, padR = 6, padT = 8, padB = 10;
            const plotX = boxX + padL;
            const plotY = boxY + padT;
            const plotW = boxW - padL - padR;
            const plotH = boxH - padT - padB;
            const yMax = 0.6;

            const xPos = (i) => plotX + (plotW * i) / (monthData.length - 1);
            const yPos = (v) => plotY + plotH - (plotH * v) / yMax;

            // grid + Y labels
            pdf.setFontSize(7);
            pdf.setFont("helvetica", "normal");
            [0, 0.2, 0.4, 0.6].forEach(tick => {
                const yy = yPos(tick);
                pdf.setDrawColor(226, 232, 240);
                pdf.setLineDashPattern([1, 1], 0);
                pdf.line(plotX, yy, plotX + plotW, yy);
                pdf.setLineDashPattern([], 0);
                pdf.setTextColor(100, 116, 139);
                pdf.text(tick.toFixed(1), boxX + 2, yy + 1.5);
            });

            // X labels (short month names to fit)
            const shortLabels = ["Dec 25", "Jan 26", "Mar 26", "Jun 26"];
            pdf.setTextColor(30, 58, 138);
            pdf.setFont("helvetica", "bold");
            monthData.forEach((d, i) => {
                const xx = xPos(i);
                const label = shortLabels[i] || d.label;
                pdf.text(label, xx, plotY + plotH + 5, { align: 'center' });
            });

            // axes
            pdf.setDrawColor(203, 213, 225);
            pdf.setLineWidth(0.3);
            pdf.line(plotX, plotY, plotX, plotY + plotH); // Y axis
            pdf.line(plotX, plotY + plotH, plotX + plotW, plotY + plotH); // X axis

            // data lines + dots + value labels
            seriesDefs.forEach(s => {
                const pts = monthData
                    .map((d, i) => ({ v: d[s.key], i }))
                    .filter(p => p.v !== null && p.v !== undefined);
                if (pts.length === 0) return;
                // line
                pdf.setDrawColor(s.rgb[0], s.rgb[1], s.rgb[2]);
                pdf.setLineWidth(0.8);
                for (let k = 1; k < pts.length; k++) {
                    pdf.line(
                        xPos(pts[k - 1].i), yPos(pts[k - 1].v),
                        xPos(pts[k].i), yPos(pts[k].v)
                    );
                }
                // dots + values
                pts.forEach(p => {
                    const xx = xPos(p.i);
                    const yy = yPos(p.v);
                    pdf.setFillColor(s.rgb[0], s.rgb[1], s.rgb[2]);
                    pdf.circle(xx, yy, 1.3, 'F');
                    pdf.setFillColor(255, 255, 255);
                    pdf.circle(xx, yy, 0.5, 'F');
                    pdf.setFontSize(7);
                    pdf.setTextColor(s.rgb[0], s.rgb[1], s.rgb[2]);
                    pdf.setFont("helvetica", "bold");
                    pdf.text(p.v.toFixed(2), xx, yy - 3, { align: 'center' });
                });
            });
            pdf.setLineWidth(0.2);

            currentY += boxH + 8;
        }

        addFooter();
        pdf.save(`Water_Quality_Report_${currentData.id}.pdf`);
    } catch (error) {
        console.error("Could not generate PDF", error);
    }
    setIsGeneratingPdf(false);
  };

  return (
    <div className="min-h-screen bg-[#f5f7f9] text-[#1e3a8a] font-sans p-6 flex flex-col gap-6 overflow-auto">
      
      {/* HEADER */}
      <header className="flex flex-col lg:flex-row lg:items-center gap-6 justify-between bg-white p-6 rounded-xl border border-[#e2e8f0] shadow-sm">
        <div className="flex items-center gap-4">
            <div className="w-14 h-14 bg-[#e6f0ff] rounded-xl flex items-center justify-center">
                <Waves size={32} className="text-[#3b82f6]" strokeWidth={2.5} />
            </div>
            <div>
                <h1 className="text-[24px] font-bold text-[#1e3a8a] leading-tight">Backwater Water Quality</h1>
                <p className="text-[13px] text-[#64748b] mt-0.5">Satellite-Based Detection and Change Tracking</p>
            </div>
        </div>
        <div className="flex items-center gap-4">
            <div className="hidden md:flex bg-[#e6f0ff] text-[#1e3a8a] px-4 py-2 rounded-lg items-center gap-2 border border-[#dbeafe]">
                <MapPin size={16} className="text-[#3b82f6]"/> 
                <span className="text-[13px] font-semibold">10.02°N, 76.31°E</span>
            </div>
            <button 
                onClick={generatePDF}
                disabled={isGeneratingPdf}
                className="bg-[#3b82f6] hover:bg-[#2563eb] text-white px-5 py-2.5 rounded-lg font-bold text-[13px] transition-colors flex items-center gap-2 shadow-sm disabled:opacity-50"
            >
                {isGeneratingPdf ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                )}
                {isGeneratingPdf ? 'Generating...' : 'Download Report'}
            </button>
        </div>
      </header>
      
      {/* MAIN LAYOUT */}
      <div id="dashboard-content" className="flex flex-col xl:flex-row gap-6 flex-1 bg-[#f5f7f9] pb-4">
        
        {/* MIDDLE CONTENT */}
        <main className="flex-1 flex flex-col gap-4 min-w-0">
           
           {/* Select Dates / View */}
           <div className="flex flex-col sm:flex-row gap-4">
              <div className="bg-white border border-[#e2e8f0] rounded-xl p-3 flex-1 flex flex-col gap-2">
                 <div className="flex justify-between items-center px-1">
                     <div className="flex items-center gap-2 text-[13px] font-bold text-[#1e3a8a]">
                         <CalendarIcon size={16} className="text-[#1e3a8a]"/> Select Dates <span className="text-[#64748b] text-[11px] font-normal">(at least 3)</span>
                     </div>
                     <button 
                        onClick={() => setIsPlaying(!isPlaying)}
                        className={`flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-full transition-colors ${isPlaying ? 'bg-red-100 text-red-600 hover:bg-red-200' : 'bg-green-100 text-green-600 hover:bg-green-200'}`}
                     >
                        {isPlaying ? <Pause size={14} fill="currentColor"/> : <Play size={14} fill="currentColor"/>} 
                        {isPlaying ? 'Pause' : 'Play Animation'}
                     </button>
                 </div>
                 <div className="flex gap-2">
                    {dateLabels.map((date, idx) => (
                        <button 
                            key={idx}
                            onClick={() => { setCurrentIndex(idx); setIsPlaying(false); }}
                            className={`flex-1 py-1.5 text-[13px] font-semibold border rounded transition-colors ${currentIndex === idx ? 'bg-[#3b82f6] text-white border-[#3b82f6] shadow-sm' : 'border-[#cbd5e1] text-[#1e3a8a] bg-white hover:bg-[#f8fafc]'}`}
                        >
                            {date}
                        </button>
                    ))}
                 </div>
              </div>
              <div className="bg-white border border-[#e2e8f0] rounded-xl p-3 w-full sm:w-64 flex flex-col gap-2">
                 <div className="flex items-center gap-2 text-[13px] font-bold text-[#1e3a8a] px-1">
                     <MapIcon size={16} className="text-[#1e3a8a]"/> View
                 </div>
                 <div className="relative">
                    <select className="w-full py-1.5 pl-3 pr-8 text-[13px] font-semibold border border-[#cbd5e1] rounded text-[#1e3a8a] appearance-none outline-none focus:ring-2 focus:ring-[#3b82f6]/50 bg-white">
                        <option>Water Quality Map</option>
                    </select>
                    <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none">
                        <svg className="w-4 h-4 text-[#64748b]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                    </div>
                 </div>
              </div>
           </div>

           {/* Water Quality Map (LARGE SINGLE MAP) */}
           <div className="bg-white border border-[#e2e8f0] rounded-xl p-4 flex flex-col gap-3">
               <div className="flex items-center gap-2 text-[17px] font-bold text-[#1e3a8a]">
                   Water Quality Map <span className="text-xs font-normal text-[#3b82f6]">(Only water areas are shown, land is masked)</span>
               </div>
               
                <div className="flex flex-col md:flex-row gap-4 h-[340px]">
                   {/* Single Big Animated Map */}
                   <div id="map-capture" className="flex-1 rounded border border-[#cbd5e1] relative overflow-hidden h-full shadow-inner">
                      <RealImageMap type={currentType} isChangeMap={false} />
                      
                      {/* Playback Badge Overlay */}
                      {isPlaying && (
                        <div className="absolute top-4 right-4 bg-white/90 text-[#1e3a8a] font-bold px-3 py-1.5 rounded-lg shadow-md border border-[#cbd5e1] backdrop-blur text-sm flex items-center gap-2 z-10">
                            <span className="w-3 h-3 rounded-full bg-[#ef4444] animate-pulse"></span>
                            Showing: {dateLabels[currentIndex]}
                        </div>
                      )}

                      <div className="absolute top-4 right-6 flex flex-col items-center z-10">
                          <div className="text-[11px] font-bold text-white drop-shadow-[0_1px_2px_rgba(0,0,0,1)]">N</div>
                          <div className="text-white drop-shadow-[0_1px_2px_rgba(0,0,0,1)] text-sm">▲</div>
                      </div>
                      <div className="absolute bottom-3 left-3 flex items-end gap-1 text-[11px] text-white drop-shadow-[0_1px_2px_rgba(0,0,0,1)] font-medium z-10">
                          <span>0</span><div className="w-8 border-b-[1.5px] border-white mb-[2px]"></div>
                          <span>0.25</span><div className="w-8 border-b-[1.5px] border-white mb-[2px]"></div>
                          <span>0.5</span><div className="w-16 border-b-[1.5px] border-white mb-[2px]"></div>
                          <span>1 km</span>
                      </div>
                  </div>
                  
                  {/* Map Legend (Location Labels style) */}
                  <div className="w-full md:w-[170px] flex flex-col justify-between border-t md:border-t-0 md:border-l border-[#e2e8f0] pt-4 md:pt-0 md:pl-4">
                     <div>
                         <div className="text-[13px] font-bold text-[#1e3a8a] mb-3">Water Quality</div>
                         
                         <div className="flex flex-col gap-3">
                            <div className="flex items-center gap-3"><div className="w-6 h-6 bg-[#1d4ed8] rounded-md shadow-sm"></div><span className="text-[11px] font-medium text-[#1e3a8a]">Better / Cleaner</span></div>
                            <div className="flex items-center gap-3"><div className="w-6 h-6 bg-[#22c55e] rounded-md shadow-sm"></div><span className="text-[11px] font-medium text-[#1e3a8a]">Moderate</span></div>
                            <div className="flex items-center gap-3"><div className="w-6 h-6 bg-[#eab308] rounded-md shadow-sm"></div><span className="text-[11px] font-medium text-[#1e3a8a] leading-tight">More Turbid<br/><span className="text-[9px] text-[#64748b] font-normal">(or changed)</span></span></div>
                            <div className="flex items-center gap-3"><div className="w-6 h-6 bg-[#ef4444] rounded-md shadow-sm"></div><span className="text-[11px] font-medium text-[#1e3a8a]">Highest change</span></div>
                         </div>
                         
                         <div className="flex flex-col gap-3 mt-4">
                            <div className="flex items-center gap-3">
                                <div className="w-6 h-6 rounded-md shadow-sm overflow-hidden" style={{backgroundImage: "url('/periyar-satellite.jpg')", backgroundSize: '300%'}}></div>
                                <span className="text-[11px] font-medium text-[#1e3a8a] leading-tight">Land<br/><span className="text-[9px] text-[#64748b] font-normal">(masked)</span></span>
                            </div>
                         </div>
                     </div>
                     
                     <div className="mt-4 pt-4 border-t border-[#e2e8f0]">
                         <div className="text-[13px] font-bold text-[#1e3a8a] mb-2">Location Labels</div>
                         <div className="flex flex-col gap-2">
                            <div className="flex items-center gap-2 text-[11px] text-[#1e3a8a]"><MapPin size={14} className="text-[#1e3a8a]"/> Water body / area name</div>
                            <div className="flex items-center gap-2 text-[11px] text-[#1e3a8a]"><div className="w-3 h-0.5 bg-[#1e3a8a] ml-0.5"></div> Channel / canal</div>
                         </div>
                     </div>
                  </div>
               </div>
           </div>

           {/* Change Map & Index Trends */}
           <div className="flex flex-col xl:flex-row gap-4">
              
              {/* Change Map */}
              <div className="bg-white border border-[#e2e8f0] rounded-xl p-4 flex-1 flex flex-col min-w-0">
                  <div className="text-[15px] font-bold text-[#1e3a8a] mb-3">
                      Change Map <span className="text-xs font-normal text-[#3b82f6]">(Jan &rarr; Jun)</span>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-4 h-[180px]">
                      
                      <div className="flex-1 rounded border border-[#cbd5e1] h-full relative overflow-hidden shadow-inner">
                          <RealImageMap type="change" isChangeMap={true} />
                          <div className="absolute top-2 right-2 flex flex-col items-center z-10">
                              <div className="text-[9px] font-bold text-white drop-shadow-[0_1px_2px_rgba(0,0,0,1)]">N</div>
                              <div className="text-white drop-shadow-[0_1px_2px_rgba(0,0,0,1)] text-[10px]">▲</div>
                          </div>
                          <div className="absolute bottom-2 left-2 flex items-end gap-0.5 text-[9px] text-white drop-shadow-[0_1px_2px_rgba(0,0,0,1)] font-medium z-10">
                              <span>0</span><div className="w-4 border-b border-white mb-1"></div>
                              <span>0.25</span><div className="w-4 border-b border-white mb-1"></div>
                              <span>0.5</span><div className="w-8 border-b border-white mb-1"></div>
                              <span>1 km</span>
                          </div>
                      </div>
                      
                      <div className="w-[140px] flex flex-col justify-center gap-2.5 pl-1">
                         <div className="flex items-start gap-2">
                             <div className="w-6 h-6 border-[2px] border-dashed border-[#ef4444] rounded-full flex-shrink-0 mt-0.5"></div>
                             <span className="text-[11px] font-semibold text-[#1e3a8a] leading-tight">Areas with<br/>significant change<br/><span className="text-[9px] text-[#64748b] font-normal">(most noticeable)</span></span>
                         </div>
                         <div className="flex items-center gap-2"><div className="w-4 h-4 bg-[#3b82f6] rounded"></div><span className="text-[11px] font-medium text-[#1e3a8a]">No change</span></div>
                         <div className="flex items-center gap-2"><div className="w-4 h-4 bg-[#22c55e] rounded"></div><span className="text-[11px] font-medium text-[#1e3a8a]">Small change</span></div>
                         <div className="flex items-center gap-2"><div className="w-4 h-4 bg-[#eab308] rounded"></div><span className="text-[11px] font-medium text-[#1e3a8a]">Moderate change</span></div>
                         <div className="flex items-center gap-2"><div className="w-4 h-4 bg-[#ef4444] rounded"></div><span className="text-[11px] font-medium text-[#1e3a8a]">High change</span></div>
                      </div>
                  </div>
              </div>
              
              {/* Index Trends */}
              <div className="bg-white border border-[#e2e8f0] rounded-xl p-4 flex-1 flex flex-col min-w-0">
                  <div className="text-[15px] font-bold text-[#1e3a8a] mb-2">
                      Index Trends <span className="text-xs font-normal text-[#3b82f6]">(average over water body)</span>
                  </div>
                  
                  <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center mb-2 gap-2">
                      <div className="flex flex-wrap gap-2">
                          <button 
                            onClick={() => setTrendTab('All')}
                            className={`px-3 py-1 text-[12px] font-semibold rounded border transition-colors ${trendTab === 'All' ? 'bg-[#1e3a8a] text-white border-[#1e3a8a]' : 'bg-[#e6f0ff] text-[#1e3a8a] border-[#bfdbfe] hover:bg-[#dbeafe]'}`}
                          >All</button>
                          <button 
                            onClick={() => setTrendTab('Turbidity')}
                            className={`px-3 py-1 text-[12px] font-semibold rounded border transition-colors ${trendTab === 'Turbidity' ? 'bg-[#3b82f6] text-white border-[#3b82f6]' : 'bg-[#e6f0ff] text-[#1e3a8a] border-[#bfdbfe] hover:bg-[#dbeafe]'}`}
                          >Turbidity</button>
                          <button 
                            onClick={() => setTrendTab('Chlorophyll')}
                            className={`px-3 py-1 text-[12px] font-semibold rounded border transition-colors ${trendTab === 'Chlorophyll' ? 'bg-[#22c55e] text-white border-[#22c55e]' : 'bg-[#e6f0ff] text-[#1e3a8a] border-[#bfdbfe] hover:bg-[#dbeafe]'}`}
                          >Chlorophyll</button>
                          <button 
                            onClick={() => setTrendTab('Suspended Sediments')}
                            className={`px-3 py-1 text-[12px] font-semibold rounded border transition-colors ${trendTab === 'Suspended Sediments' ? 'bg-[#d97706] text-white border-[#d97706]' : 'bg-[#e6f0ff] text-[#1e3a8a] border-[#bfdbfe] hover:bg-[#dbeafe]'}`}
                          >Sediments</button>
                      </div>
                      <div className="flex flex-wrap items-center gap-3 pr-2">
                         {(trendTab === 'All' || trendTab === 'Turbidity') && <div className="flex items-center gap-1.5 text-[11px] font-bold text-[#1e3a8a]"><div className="w-2 h-2 rounded-full bg-[#3b82f6]"></div> Turbidity</div>}
                         {(trendTab === 'All' || trendTab === 'Chlorophyll') && <div className="flex items-center gap-1.5 text-[11px] font-bold text-[#1e3a8a]"><div className="w-2 h-2 rounded-full bg-[#22c55e]"></div> Chlorophyll</div>}
                         {(trendTab === 'All' || trendTab === 'Suspended Sediments') && <div className="flex items-center gap-1.5 text-[11px] font-bold text-[#1e3a8a]"><div className="w-2 h-2 rounded-full bg-[#d97706]"></div> Sediments</div>}
                      </div>
                  </div>
                  
                   <div id="chart-capture" className="flex-1 w-full min-h-[140px] text-[10px] bg-white">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 15, right: 15, left: -25, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#1e3a8a', fontWeight: 600}} dy={5} />
                        <YAxis axisLine={true} stroke="#cbd5e1" tickLine={false} tick={{fill: '#1e3a8a', fontWeight: 600}} domain={[0, 0.6]} ticks={[0.0, 0.2, 0.4, 0.6]} />
                        <Tooltip />
                        {(trendTab === 'All' || trendTab === 'Turbidity') && <Line type="monotone" dataKey="turbidity" stroke="#3b82f6" strokeWidth={2} dot={{fill: '#3b82f6', strokeWidth: 2, r: 3}} label={{ position: 'top', fill: '#3b82f6', fontSize: 10, fontWeight: 'bold', dy: -5 }} />}
                        {(trendTab === 'All' || trendTab === 'Chlorophyll') && <Line type="monotone" dataKey="chlorophyll" stroke="#22c55e" strokeWidth={2} dot={{fill: '#22c55e', strokeWidth: 2, r: 3}} label={{ position: 'bottom', fill: '#22c55e', fontSize: 10, fontWeight: 'bold', dy: 8 }} />}
                        {(trendTab === 'All' || trendTab === 'Suspended Sediments') && <Line type="monotone" dataKey="suspendedSediments" stroke="#d97706" strokeWidth={2} dot={{fill: '#d97706', strokeWidth: 2, r: 3}} label={{ position: 'top', fill: '#d97706', fontSize: 10, fontWeight: 'bold', dy: -15 }} />}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
              </div>
           </div>

           {/* Bottom Alert */}
           <div className="bg-[#e6f0ff] rounded-xl p-3 flex items-center gap-3 text-[#1e3a8a] border border-[#dbeafe]">
               <Waves size={24} className="text-[#3b82f6] flex-shrink-0" strokeWidth={3}/>
               <div>
                  <div className="font-bold text-[12px]">Satellite-derived indices are proxies and are not laboratory water quality measurements.</div>
                  <div className="text-[11px] text-[#3b82f6] font-medium">They indicate possible changes in water conditions, not definitive pollution levels.</div>
               </div>
           </div>

        </main>

        {/* RIGHT SIDEBAR */}
        <aside className="w-full xl:w-[320px] flex-shrink-0 flex flex-col gap-4">
           
           {/* Quick Summary */}
           <div className="bg-white border border-[#e2e8f0] rounded-xl p-5 flex flex-col gap-4">
              <div className="text-[17px] font-bold text-[#1e3a8a]">Quick Summary</div>
              
              <div className="flex items-center gap-4">
                 <Cloud size={44} className="text-[#3b82f6] fill-[#dbeafe] stroke-1"/>
                 <div>
                    <div className="text-[12px] text-[#1e3a8a] font-medium">Cloud coverage <span className="text-[#3b82f6]">({currentData.label})</span></div>
                    <div className="text-[28px] font-bold text-[#1e3a8a] leading-none mt-1">{currentData.cloudCoverage}%</div>
                    {currentData.isCloudy && <div className="text-[10px] text-[#64748b]">(limits analysis)</div>}
                 </div>
              </div>
              
              <div className="flex items-center gap-4 mt-1">
                 <Droplet size={36} className="text-[#3b82f6] fill-[#3b82f6] ml-1"/>
                 <div className="ml-1">
                    <div className="text-[12px] text-[#1e3a8a] font-medium">Valid water pixels <span className="text-[#3b82f6]">({currentData.label})</span></div>
                    <div className="text-[28px] font-bold text-[#1e3a8a] leading-none mt-1">{currentData.validPixels}%</div>
                 </div>
              </div>

              <div className="flex items-center gap-4 mt-1 mb-1">
                 <AlertTriangle size={36} className="text-[#ef4444] fill-[#fecaca] ml-1"/>
                 <div className="ml-1">
                    <div className="text-[12px] text-[#1e3a8a] font-medium">Polluted Area <span className="text-[#3b82f6]">({currentData.label})</span></div>
                    <div className="text-[28px] font-bold text-[#ef4444] leading-none mt-1">{currentData.pollutedPercent !== null ? currentData.pollutedPercent + '%' : 'N/A'}</div>
                 </div>
              </div>

              {currentData.isCloudy && (
                 <div className="bg-[#fffbeb] border border-[#fde047] rounded-xl p-3 flex items-start gap-3 mt-1">
                    <AlertTriangle size={20} className="text-[#eab308] flex-shrink-0 fill-[#fef08a] mt-0.5"/>
                    <div className="text-[11px] text-[#1e3a8a] leading-relaxed">
                       <span className="font-bold">Cloudy - not enough information to come to conclusion.</span><br/>
                       <span className="text-[#1e3a8a] font-medium">These areas are shown in grey on the map.</span>
                    </div>
                 </div>
              )}
           </div>

           {/* Index Values */}
           <div className="bg-white border border-[#e2e8f0] rounded-xl p-4 flex flex-col gap-4">
              <div className="flex justify-between items-end">
                  <div className="text-[17px] font-bold text-[#1e3a8a]">Index Values</div>
                  <div className="text-[11px] font-bold text-[#3b82f6] bg-[#e6f0ff] px-2 py-0.5 rounded border border-[#bfdbfe]">{currentData.label}</div>
              </div>
              
              <div className="flex flex-col gap-3">
                 <div className="flex items-center justify-between bg-[#f8fafc] rounded-lg border border-[#e2e8f0] p-3 shadow-sm">
                    <div>
                        <div className="flex items-center gap-1.5 text-[13px] font-bold text-[#1e3a8a] mb-0.5">
                            <Droplet size={14} className="text-[#3b82f6] fill-[#3b82f6]"/> Turbidity
                        </div>
                        <div className="text-[10px] text-[#64748b]">(higher = murkier)</div>
                    </div>
                    <div className="text-[24px] font-bold text-[#1e3a8a]">{currentData.turbidity !== null ? currentData.turbidity.toFixed(2) : 'N/A'}</div>
                 </div>

                 <div className="flex items-center justify-between bg-[#f8fafc] rounded-lg border border-[#e2e8f0] p-3 shadow-sm">
                    <div>
                        <div className="flex items-center gap-1.5 text-[13px] font-bold text-[#1e3a8a] mb-0.5">
                            <Leaf size={14} className="text-[#22c55e] fill-[#22c55e]"/> Chlorophyll
                        </div>
                        <div className="text-[10px] text-[#64748b]">(higher = algae)</div>
                    </div>
                    <div className="text-[24px] font-bold text-[#1e3a8a]">{currentData.chlorophyll !== null ? currentData.chlorophyll.toFixed(2) : 'N/A'}</div>
                 </div>

                 <div className="flex items-center justify-between bg-[#f8fafc] rounded-lg border border-[#e2e8f0] p-3 shadow-sm">
                    <div>
                        <div className="flex items-center gap-1.5 text-[13px] font-bold text-[#1e3a8a] mb-0.5">
                            <Waves size={14} className="text-[#d97706]"/> Sediments
                        </div>
                        <div className="text-[10px] text-[#64748b]">(higher = sediment)</div>
                    </div>
                    <div className="text-[24px] font-bold text-[#1e3a8a]">{currentData.suspendedSediments !== null ? currentData.suspendedSediments.toFixed(2) : 'N/A'}</div>
                 </div>
              </div>
           </div>

           {/* What does this mean? */}
           <div className="bg-[#e6f0ff] rounded-xl p-4 flex flex-col gap-3 flex-1 border border-[#dbeafe]">
              <div className="flex items-center gap-2 text-[15px] font-bold text-[#1e3a8a]">
                 <div className="bg-[#3b82f6] text-white rounded-full p-1 shadow-sm"><HelpCircle size={14} strokeWidth={2.5}/></div> What does this mean?
              </div>
              <ul className="text-[12px] text-[#1e3a8a] space-y-2.5 list-disc pl-5 font-medium marker:text-[#3b82f6] leading-relaxed">
                 <li><span className="font-bold">Turbidity</span> and chlorophyll indices <span className="font-bold">increased</span> from January to June.</li>
                 <li>The largest change is seen <span className="font-bold">in the central part</span> of the backwater.</li>
                 <li>Cloud cover in June limits full analysis (32%).</li>
              </ul>
           </div>
        </aside>
      </div>
    </div>
  );
}
