let currentThreadId = null;

async function predictTraffic() {
    let origin = document.getElementById("origin").value;
    let destination = document.getElementById("destination").value;
    let day = document.getElementById("pred_day").value;
    let time = document.getElementById("pred_time").value;

    if (!origin.trim() || !destination.trim()) {
        alert("Please enter both origin and destination");
        return;
    }

    if (window.UI) window.UI.startProgress();

    try {
        let statusMsg = `
            <div class="flex items-center gap-2 text-white">
                <span class="material-symbols-outlined text-sm animate-spin">sync</span>
                <span>Checking traffic from <span class="font-bold">${origin}</span> to <span class="font-bold">${destination}</span>${day !== "now" ? ` for <span class="font-bold">${day}</span>` : ""}${time ? ` at <span class="font-bold">${time}</span>` : ""}...</span>
            </div>
        `;
        displayMessage(statusMsg, "user");

        let bodyParams = { origin, destination, day, time };
        if (currentThreadId) {
            bodyParams.thread_id = currentThreadId;
        }

        let response = await fetch("/predict/", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: new URLSearchParams(bodyParams)
        });

        let data = await response.json();
        console.log("DEBUG: Frontend received prediction data:", data);

        if (data.error) {
            displayMessage(`
                <div class="flex items-center gap-3 text-error">
                    <span class="material-symbols-outlined">error</span>
                    <p class="font-bold">Error: ${data.error}</p>
                </div>
            `, "bot");
            return;
        }

    if (data.thread_id) {
        if (!currentThreadId) {
            currentThreadId = data.thread_id;
            loadChatThreads(); // Refresh history list to show the new thread
        }
    }

    let interpretation = "";
    let suggestion = "";
    let statusEmoji = "";
    let headerColor = "";

    if (data.congestion === 'Low') {
        interpretation = "You're good to go! The roads are looking clear.";
        suggestion = "It's a great time to start your journey. Drive safely!";
        statusEmoji = "🟢";
        headerColor = "text-green-700";
    } else if (data.congestion === 'Medium') {
        interpretation = "Expect some light traffic.";
        suggestion = "It's not too bad, but maybe leave a few minutes earlier just to be safe!";
        if (data.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 rounded-lg border border-blue-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> If you can, leave at <b>${data.recommended_departure.time}</b> for <b>${data.recommended_departure.congestion}</b> traffic (${data.recommended_departure.travel_time} mins).
            </span>`;
        }
        statusEmoji = "🟡";
        headerColor = "text-yellow-700";
    } else {
        interpretation = "Expect delays! Heavy traffic detected.";
        suggestion = "Consider waiting a bit or taking an alternative route if possible.";
        if (data.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded-lg border border-green-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> A better time to leave is <b>${data.recommended_departure.time}</b> (${data.recommended_departure.travel_time} mins, <b>${data.recommended_departure.congestion}</b> traffic).
            </span>`;
        }
            statusEmoji = "🔴";
            headerColor = "text-red-700";
        }

        let botReply = `
        <div class="flex flex-col gap-6 w-full font-sans text-on-surface">
            <!-- Header Section with Badge -->
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <div class="p-2 bg-primary/10 rounded-lg">
                        <span class="material-symbols-outlined text-primary">${data.is_prediction ? "auto_graph" : "on_device_training"}</span>
                    </div>
                    <div>
                        <h3 class="font-headline font-bold text-lg leading-none">${data.is_prediction ? "Smart Forecast" : "Live Traffic Update"}</h3>
                        <p class="text-xs text-on-surface-variant">${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} • Verified Source</p>
                    </div>
                </div>
                <div class="flex items-center gap-1.5 px-3 py-1 rounded-full ${data.congestion === 'Low' ? 'bg-green-100 text-green-700' : data.congestion === 'Medium' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'} border border-current/20">
                    <span class="w-2 h-2 rounded-full bg-current animate-pulse"></span>
                    <span class="text-xs font-bold uppercase tracking-wider">${data.congestion} Traffic</span>
                </div>
            </div>

            <!-- Summary Card -->
            <div class="bg-white rounded-3xl p-6 border border-outline-variant/30 shadow-xl shadow-primary/5">
                <p class="text-sm text-on-surface-variant mb-6">
                    I've analyzed the route from <span class="text-on-surface font-semibold underline decoration-primary/20">${origin}</span> to <span class="text-on-surface font-semibold underline decoration-primary/20">${destination}</span>.
                    ${data.is_prediction ? `Forecast for <b>${data.day}</b> at <b>${data.hour}:00</b>:` : "Current status:"}
                </p>

                <!-- Key Metrics Grid -->
                <div class="grid grid-cols-2 gap-4 mb-6">
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Travel Time</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-primary">${data.travel_time || 'N/A'}</span>
                            <span class="text-sm font-bold text-primary/60">mins</span>
                        </div>
                    </div>
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Distance</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-on-surface">${data.distance || 'N/A'}</span>
                            <span class="text-sm font-bold text-on-surface-variant">km</span>
                        </div>
                    </div>
                </div>

                <!-- Status Interpretation -->
                <div class="flex items-start gap-4 p-4 rounded-2xl ${data.congestion === 'Low' ? 'bg-green-50' : data.congestion === 'Medium' ? 'bg-yellow-50' : 'bg-red-50'} mb-6">
                    <span class="text-3xl">${statusEmoji}</span>
                    <div>
                        <p class="font-bold text-on-surface leading-tight mb-1">${interpretation}</p>
                        <p class="text-sm text-on-surface-variant leading-relaxed">${suggestion}</p>
                    </div>
                </div>

                <!-- Technical Details Accordion-like list -->
                <div class="space-y-3 pt-4 border-t border-outline-variant/20">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">speed</span>
                            <span class="text-xs font-medium text-on-surface-variant">Average Speed</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${data.speed || 'N/A'} km/h</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">history</span>
                            <span class="text-xs font-medium text-on-surface-variant">Normal Duration</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${data.normal_duration || 'N/A'} mins</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">verified</span>
                            <span class="text-xs font-medium text-on-surface-variant">ML Confidence</span>
                        </div>
                        <div class="flex items-center gap-1">
                            <span class="text-xs font-bold text-primary">${data.confidence_score}%</span>
                            <div class="flex gap-0.5">
                                <div class="w-1 h-3 rounded-full ${data.confidence_score > 70 ? 'bg-primary' : 'bg-primary/20'}"></div>
                                <div class="w-1 h-3 rounded-full ${data.confidence_score > 85 ? 'bg-primary' : 'bg-primary/20'}"></div>
                                <div class="w-1 h-3 rounded-full ${data.confidence_score > 90 ? 'bg-primary' : 'bg-primary/20'}"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- NEW: Google vs AI Comparison -->
                <div class="mt-6 pt-6 border-t border-outline-variant/20">
                    <h4 class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-4">Hybrid AI Analysis</h4>
                    <div class="space-y-4">
                        <div class="flex justify-between items-center bg-surface-container-lowest p-3 rounded-xl border border-outline-variant/10">
                            <div>
                                <p class="text-[10px] text-on-surface-variant uppercase font-bold">Google Maps ETA</p>
                                <p class="text-sm font-bold">${data.google_traffic_duration} mins</p>
                            </div>
                            <div class="text-right">
                                <p class="text-[10px] text-on-surface-variant uppercase font-bold">AI Adjustment</p>
                                <p class="text-sm font-bold ${data.ai_adjustment > 0 ? 'text-error' : (data.ai_adjustment < 0 ? 'text-green-600' : 'text-on-surface')}">
                                    ${data.ai_adjustment > 0 ? '+' : ''}${data.ai_adjustment} mins
                                </p>
                            </div>
                        </div>
                        ${data.adjustment_reasons && data.adjustment_reasons.length > 0 ? `
                        <div class="px-3">
                            <ul class="space-y-1">
                                ${data.adjustment_reasons.map(reason => `
                                    <li class="flex items-center gap-2 text-[11px] text-on-surface-variant">
                                        <span class="w-1 h-1 rounded-full bg-primary/40"></span>
                                        ${reason}
                                    </li>
                                `).join('')}
                            </ul>
                        </div>
                        ` : ''}
                        <div class="bg-primary/5 p-4 rounded-2xl border border-primary/10 flex justify-between items-center">
                            <span class="text-xs font-bold text-primary uppercase tracking-wider">Final Smart ETA</span>
                            <span class="text-xl font-black text-primary">${data.final_smart_eta} mins</span>
                        </div>
                    </div>
                </div>

                <!-- NEW: Traffic Pressure & Risk -->
                <div class="mt-6 pt-6 border-t border-outline-variant/20 grid grid-cols-2 gap-4">
                    <div>
                        <h4 class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-2">Pressure Score</h4>
                        <div class="flex items-center gap-2">
                            <div class="flex-1 h-1.5 bg-surface-container-high rounded-full overflow-hidden">
                                <div class="h-full ${data.traffic_pressure_score > 70 ? 'bg-red-500' : (data.traffic_pressure_score > 35 ? 'bg-yellow-500' : 'bg-green-500')}" style="width: ${data.traffic_pressure_score}%"></div>
                            </div>
                            <span class="text-xs font-bold">${data.traffic_pressure_score}/100</span>
                        </div>
                        <p class="text-[10px] text-on-surface-variant mt-1">${data.pressure_level} Pressure Environment</p>
                    </div>
                    <div>
                        <h4 class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-2">Route Risk</h4>
                        <div class="flex items-center gap-1.5">
                            <span class="material-symbols-outlined text-sm ${data.risk_analysis.level === 'High' ? 'text-red-500' : (data.risk_analysis.level === 'Medium' ? 'text-yellow-500' : 'text-green-500')}">
                                ${data.risk_analysis.level === 'High' ? 'warning' : (data.risk_analysis.level === 'Medium' ? 'info' : 'check_circle')}
                            </span>
                            <span class="text-xs font-bold text-on-surface">${data.risk_analysis.level} Risk</span>
                        </div>
                        <p class="text-[10px] text-on-surface-variant mt-1">Stability: ${data.risk_analysis.stability}</p>
                    </div>
                </div>

                <!-- NEW: Contextual Analysis -->
                <div class="mt-6 pt-6 border-t border-outline-variant/20">
                    <h4 class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-4">Context Intelligence</h4>
                    <div class="grid grid-cols-3 gap-2">
                        <div class="p-2 bg-surface-container-lowest rounded-xl border border-outline-variant/10 flex flex-col items-center text-center">
                            <span class="material-symbols-outlined text-sm text-primary mb-1">cloud</span>
                            <span class="text-[9px] text-on-surface-variant uppercase font-bold">Weather</span>
                            <span class="text-[10px] font-bold">${data.context_analysis.weather}</span>
                        </div>
                        <div class="p-2 bg-surface-container-lowest rounded-xl border border-outline-variant/10 flex flex-col items-center text-center">
                            <span class="material-symbols-outlined text-sm text-primary mb-1">school</span>
                            <span class="text-[9px] text-on-surface-variant uppercase font-bold">School</span>
                            <span class="text-[10px] font-bold">${data.context_analysis.school_rush === 'Yes' ? 'Rush Hour' : 'No Rush'}</span>
                        </div>
                        <div class="p-2 bg-surface-container-lowest rounded-xl border border-outline-variant/10 flex flex-col items-center text-center">
                            <span class="material-symbols-outlined text-sm text-primary mb-1">work</span>
                            <span class="text-[9px] text-on-surface-variant uppercase font-bold">Office</span>
                            <span class="text-[10px] font-bold">${data.context_analysis.office_rush === 'Yes' ? 'Rush Hour' : 'No Rush'}</span>
                        </div>
                    </div>
                </div>

                <!-- NEW: AI Reasoning Section -->
                <div class="mt-6 p-4 bg-surface-container-high rounded-2xl border border-outline-variant/20">
                    <h4 class="text-xs font-bold text-on-surface mb-3 flex items-center gap-2">
                        <span class="material-symbols-outlined text-sm">psychology</span>
                        Why this prediction?
                    </h4>
                    <div class="grid grid-cols-1 gap-2">
                        ${data.ai_reasoning.map(reason => `
                            <div class="flex items-center gap-2">
                                <span class="text-xs">${reason.startsWith('✓') ? '✅' : '⚠️'}</span>
                                <span class="text-xs text-on-surface-variant">${reason.substring(2)}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
    `;

    if (data.segments_delay && data.segments_delay.length > 0) {
        let delayMsg = `
            <div class="mt-2 space-y-2">
                <p class="text-xs font-bold text-error flex items-center gap-1 uppercase tracking-wider px-1">
                    <span class="material-symbols-outlined text-sm">warning</span> Segment Specific Alerts
                </p>
        `;
        data.segments_delay.forEach(seg => {
            delayMsg += `
                    <div class="p-4 bg-red-50 border-l-4 border-error rounded-r-xl flex items-start gap-3">
                        <span class="material-symbols-outlined text-error text-lg mt-0.5">report_problem</span>
                        <p class="text-xs text-on-surface leading-relaxed">
                            A little delay of <span class="font-bold text-error">${seg.delay} minutes</span> might be encountered at <span class="font-bold underline decoration-error/30">${seg.point}</span>.
                        </p>
                    </div>
            `;
        });
        delayMsg += `</div>`;
        botReply += delayMsg;
    }

    botReply += `</div>`;

        displayMessage(botReply, "bot");
    } catch (err) {
        console.error("Prediction error:", err);
        displayMessage(`
            <div class="flex items-center gap-3 text-error">
                <span class="material-symbols-outlined">error</span>
                <p class="font-bold">Error: ${err.message || 'Failed to get prediction'}</p>
            </div>
        `, "bot");
    } finally {
        if (window.UI) window.UI.stopProgress();
        if (window.TraffikLoader) {
            window.TraffikLoader.hide();
            const predictBtn = document.querySelector('button[onclick="predictTraffic()"]');
            if (predictBtn) window.TraffikLoader.revertButton(predictBtn);
        }
    }
}

async function loadChatThreads() {
    const historyList = document.getElementById("history-list");
    if (!historyList) return;

    // Show skeletons while loading
    const skeletonTemplate = document.getElementById('skeleton-table-row-template');
    if (skeletonTemplate) {
        // Create 3 skeleton rows
        let skeletonHtml = '';
        for(let i=0; i<3; i++) {
            skeletonHtml += `
                <div class="flex items-center gap-3 px-4 py-3 animate-pulse">
                    <div class="w-8 h-8 bg-slate-200 rounded-lg skeleton"></div>
                    <div class="flex-1 space-y-2">
                        <div class="h-3 bg-slate-200 rounded w-3/4 skeleton"></div>
                        <div class="h-2 bg-slate-100 rounded w-1/2 skeleton"></div>
                    </div>
                </div>
            `;
        }
        historyList.innerHTML = skeletonHtml;
    }

    try {
        const response = await fetch("/chat-history/");
        const data = await response.json();

        if (data.history && data.history.length > 0) {
            historyList.innerHTML = data.history.map(thread => `
                <div onclick="loadThread('${thread.id}')"
                     class="group flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-all hover:bg-slate-200 dark:hover:bg-slate-800 ${currentThreadId === thread.id ? 'bg-slate-200 dark:bg-slate-800' : ''} content-fade-in">
                    <span class="material-symbols-outlined text-lg text-slate-400 group-hover:text-primary transition-colors">chat_bubble</span>
                    <div class="flex-1 min-w-0">
                        <p class="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate">${thread.title}</p>
                        <p class="text-[10px] text-slate-400">${thread.timestamp}</p>
                    </div>
                </div>
            `).join("");
        } else {
            historyList.innerHTML = `<p class="px-4 py-2 text-[10px] text-slate-500 italic">No history yet</p>`;
        }
    } catch (err) {
        console.error("Error loading chat threads:", err);
    }
}

async function loadThread(threadId) {
    currentThreadId = threadId;
    document.getElementById("chatbox").innerHTML = "";

    // Update active state in sidebar
    loadChatThreads();

    try {
        const response = await fetch(`/chat-history/${threadId}/`);
        const data = await response.json();

        if (data.messages) {
            data.messages.forEach(item => {
                displayMessage(item.message, "user");
                let botReply = constructBotReply(item.response, item.timestamp);
                displayMessage(botReply, "bot");
            });
        }
    } catch (err) {
        console.error("Error loading thread:", err);
    }
}

function startNewAnalysis() {
    currentThreadId = null;
    document.getElementById("chatbox").innerHTML = "";
    document.getElementById("origin").value = "";
    document.getElementById("destination").value = "";
    document.getElementById("pred_time").value = "";
    document.getElementById("pred_day").value = "now";

    // Update sidebar UI
    loadChatThreads();

    displayMessage("New analysis started. Where would you like to go?", "bot");
}

function constructBotReply(trafficData, timestamp) {
    let interpretation = "";
    let suggestion = "";
    let statusEmoji = "";

    if (trafficData.congestion === 'Low') {
        interpretation = "You're good to go! The roads are looking clear.";
        suggestion = "It's a great time to start your journey. Drive safely!";
        statusEmoji = "🟢";
    } else if (trafficData.congestion === 'Medium') {
        interpretation = "Expect some light traffic.";
        suggestion = "It's not too bad, but maybe leave a few minutes earlier just to be safe!";
        if (trafficData.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 rounded-lg border border-blue-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> If you can, leave at <b>${trafficData.recommended_departure.time}</b> for <b>${trafficData.recommended_departure.congestion}</b> traffic (${trafficData.recommended_departure.travel_time} mins).
            </span>`;
        }
        statusEmoji = "🟡";
    } else {
        interpretation = "Expect delays! Heavy traffic detected.";
        suggestion = "Consider waiting a bit or taking an alternative route if possible.";
        if (trafficData.recommended_departure) {
            suggestion += `<br><br><span class="inline-flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded-lg border border-green-200 mt-2">
                <span class="material-symbols-outlined text-sm">schedule</span>
                <b>Tip:</b> A better time to leave is <b>${trafficData.recommended_departure.time}</b> (${trafficData.recommended_departure.travel_time} mins, <b>${trafficData.recommended_departure.congestion}</b> traffic).
            </span>`;
        }
        statusEmoji = "🔴";
    }

    let botReply = `
        <div class="flex flex-col gap-6 w-full font-sans text-on-surface">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <div class="p-2 bg-primary/10 rounded-lg">
                        <span class="material-symbols-outlined text-primary">${trafficData.is_prediction ? "auto_graph" : "on_device_training"}</span>
                    </div>
                    <div>
                        <h3 class="font-headline font-bold text-lg leading-none">${trafficData.is_prediction ? "Smart Forecast" : "Live Traffic Update"}</h3>
                        <p class="text-xs text-on-surface-variant">${timestamp || 'Verified Source'}</p>
                    </div>
                </div>
                <div class="flex items-center gap-1.5 px-3 py-1 rounded-full ${trafficData.congestion === 'Low' ? 'bg-green-100 text-green-700' : trafficData.congestion === 'Medium' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'} border border-current/20">
                    <span class="w-2 h-2 rounded-full bg-current"></span>
                    <span class="text-xs font-bold uppercase tracking-wider">${trafficData.congestion} Traffic</span>
                </div>
            </div>

            <div class="bg-white rounded-3xl p-6 border border-outline-variant/30 shadow-xl shadow-primary/5">
                <p class="text-sm text-on-surface-variant mb-6">
                    I analyzed the route from <span class="text-on-surface font-semibold underline decoration-primary/20">${trafficData.route.split('-')[0]}</span> to <span class="text-on-surface font-semibold underline decoration-primary/20">${trafficData.route.split('-')[1]}</span>.
                    ${trafficData.is_prediction ? `Forecast for <b>${trafficData.day}</b> at <b>${trafficData.hour}:00</b>:` : "Status at that time:"}
                </p>

                <div class="grid grid-cols-2 gap-4 mb-6">
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Travel Time</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-primary">${trafficData.travel_time || 'N/A'}</span>
                            <span class="text-sm font-bold text-primary/60">mins</span>
                        </div>
                    </div>
                    <div class="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10">
                        <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold mb-1">Distance</p>
                        <div class="flex items-baseline gap-1">
                            <span class="text-3xl font-black text-on-surface">${trafficData.distance || 'N/A'}</span>
                            <span class="text-sm font-bold text-on-surface-variant">km</span>
                        </div>
                    </div>
                </div>

                <div class="flex items-start gap-4 p-4 rounded-2xl ${trafficData.congestion === 'Low' ? 'bg-green-50' : trafficData.congestion === 'Medium' ? 'bg-yellow-50' : 'bg-red-50'}">
                    <span class="text-3xl">${statusEmoji}</span>
                    <div>
                        <p class="font-bold text-on-surface leading-tight mb-1">${interpretation}</p>
                        <p class="text-sm text-on-surface-variant leading-relaxed">${suggestion}</p>
                    </div>
                </div>

                <!-- Technical Details Accordion-like list -->
                <div class="space-y-3 pt-4 border-t border-outline-variant/20 mt-4">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">speed</span>
                            <span class="text-xs font-medium text-on-surface-variant">Average Speed</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${trafficData.speed || 'N/A'} km/h</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">history</span>
                            <span class="text-xs font-medium text-on-surface-variant">Normal Duration</span>
                        </div>
                        <span class="text-xs font-bold text-on-surface">${trafficData.normal_duration || 'N/A'} mins</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    return botReply;
}


function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        let cookies = document.cookie.split(";");
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function displayMessage(msg, sender) {
    let chatBox = document.getElementById("chatbox");

    let bubble;

    if (sender === "user") {
        bubble = `
        <div class="flex justify-end content-fade-in">
            <div class="bg-primary-container text-on-primary-container p-4 rounded-2xl rounded-tr-none shadow-sm max-w-[85%] md:max-w-[70%]">
                <p class="text-sm font-medium">${msg}</p>
            </div>
        </div>`;
    } else {
        bubble = `
        <div class="flex justify-start content-fade-in">
            <div class="bg-white border border-outline-variant/20 p-5 rounded-2xl rounded-tl-none shadow-md w-full max-w-[95%] md:max-w-[85%] text-on-surface">
                ${msg}
            </div>
        </div>`;
    }

    chatBox.insertAdjacentHTML('beforeend', bubble);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// document.getElementById("message") is no longer in dashboard.html
// if (document.getElementById("message")) { ... }


function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken"))
        ?.split("=")[1];
}


// ── Audio Recording ──────────────────────────────────────────
let mediaRecorder = null;
let audioChunks   = [];
let isRecording   = false;

const micBtn = document.querySelector('[data-icon="mic"]');

// Voice input is intentionally disabled: there is no /transcribe/ backend
// endpoint, so the previous recording flow always failed with a 404. The mic
// button now shows a friendly notice instead of attempting a broken upload.
if (micBtn) {
    micBtn.title = "Voice input coming soon";
    micBtn.addEventListener("click", () => {
        if (typeof displayMessage === "function") {
            displayMessage("🎙 Voice input isn't available yet — please type your route.", "bot");
        }
    });
}

// View password
const passwordInput = document.getElementById("password");
const togglePassword = document.getElementById("togglePassword");

if (passwordInput && togglePassword) {
    const icon = togglePassword.querySelector("span");
    togglePassword.addEventListener("click", () => {
        const isPassword = passwordInput.type === "password";
        passwordInput.type = isPassword ? "text" : "password";
        icon.textContent = isPassword ? "visibility_off" : "visibility";
        icon.setAttribute("data-icon", isPassword ? "visibility_off" : "visibility");
    });
}

function initAutocomplete() {
    if (typeof google === 'undefined' || !google.maps || !google.maps.places) {
        console.error("Google Maps API not loaded");
        return;
    }
    // Bias results towards Buea, Cameroon
    const buea = new google.maps.LatLng(4.1522, 9.2314);
    const options = {
        componentRestrictions: { country: "cm" },
        fields: ["address_components", "geometry", "name", "formatted_address"],
        location: buea,
        radius: 10000, // 10km radius for biasing
        strictBounds: false
    };

    // Initialize for Origin
    const originInput = document.getElementById('origin');
    if (originInput) {
        new google.maps.places.Autocomplete(originInput, options);
    }

    // Initialize for Destination
    const destInput = document.getElementById('destination');
    if (destInput) {
        new google.maps.places.Autocomplete(destInput, options);
    }
}

// Run the initialization
if (typeof google !== 'undefined' && google.maps && google.maps.event) {
    google.maps.event.addDomListener(window, 'load', initAutocomplete);
} else {
    // If API script is not yet loaded, it will be handled by the callback in the URL
    window.addEventListener('load', initAutocomplete);
}

// ── Alerts System ──────────────────────────────────────────
// The gridlock-alerts feature is not enabled: there is no /alerts/ endpoint
// (it's commented out in urls.py), so the previous 2-minute poll only produced
// 404s. Polling removed until the backend endpoint is implemented.

loadChatThreads();
