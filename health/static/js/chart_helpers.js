/*
anything custom for charts and plotting will add here
*/

document.addEventListener("DOMContentLoaded", function () {

    // const scoreData = JSON.parse(document.getElementById("scoreChart").dataset.chart);
    const scoreData = JSON.parse(document.getElementById("score-data").textContent);
    console.log("Parsed Score Data:", scoreData);
    // const weightData = JSON.parse(document.getElementById("weightChart").dataset.chart);
    const weightData = JSON.parse(document.getElementById("weight-data").textContent);
    console.log("Parsed Weight Data:", weightData);

    const scoreCanvas = document.getElementById("scoreChart");
    const weightCanvas = document.getElementById("weightChart");
    const activityCanvas = document.getElementById("activityChart");

    const goalWeight = JSON.parse(document.getElementById("goal-weight").textContent);
    const targetDate = JSON.parse(document.getElementById("target-date").textContent);
    const startDate = JSON.parse(document.getElementById("start-date").textContent);
    const startWeight = JSON.parse(document.getElementById("start-weight").textContent);

    const trendlineData = [
        { x: startDate, y: startWeight },
        { x: targetDate, y: goalWeight }
    ];

    const trendlineDataset = {
        label: 'Target Trend',
        data: trendlineData,
        borderColor: 'rgba(0, 0, 0, 0.6)',
        borderDash: [6, 6],
        borderWidth: 2,
        fill: false,
        pointRadius: 0,
        showLine: true,
        tension: 0
    };

    // placeholder UI
    Chart.register({
        id: 'noDataPlugin',
        beforeDraw(chart) {
            const data = chart.data.datasets[0]?.data || [];
            if (!data.length || data.every(d => d === null)) {
                const ctx = chart.ctx;
                const { width, height } = chart;
                ctx.save();
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.font = '16px sans-serif';
                ctx.fillStyle = '#999';
                ctx.fillText('Calculating your future as we speak...or waiting for you to add data', width / 2, height / 2);
                ctx.restore();
            }
        }
    });

    if (scoreCanvas && weightCanvas && activityCanvas) {

        const rawActivityData = JSON.parse(document.getElementById("activity-data").textContent);

        const levels = ["Sedentary", "Lightly active", "Active", "Very active", "Endurance athlete"];
        const getLevelIndex = label => {
            for (let i = 0; i < levels.length; i++) {
                if (label.startsWith(levels[i])) return i;
            }
            return -1;
        };

        const dataPoints = rawActivityData.data.map(d => ({
            x: d.x,
            y: getLevelIndex(d.y),
            label: d.y
        }));

        try {

            // healt score
            new Chart(scoreCanvas, {

                type: 'line',
                data: {
                    labels: scoreData.labels,
                    datasets: [{
                        label: 'Wellness Score',
                        data: scoreData.data,
                        borderColor: 'rgba(75, 192, 192, 1)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.3,
                        spanGaps: true,
                        showLine: false,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    }]
                },

                options: {
                    responsive: true,
                    scales: {
                        y: {
                            suggestedMin: 0, // baseline is set to 100
                            suggestedMax: 200 // same
                        }
                    }
                }

            });

            // weight grpah
            new Chart(weightCanvas, {

                type: 'line',
                data: {
                    labels: weightData.labels,
                    datasets: [{
                        label: 'Weight (kg)',
                        data: weightData.data,
                        borderColor: 'rgba(255, 99, 132, 1)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.3,
                        spanGaps: true,
                        showLine: false,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    }, trendlineDataset]
                },

                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: false
                        }
                    }
                }

            });

            //  activity stuff from form
            new Chart(activityCanvas, {

                type: 'scatter',
                data: {
                    datasets: [{
                        label: 'Daily Activity Level',
                        data: dataPoints,
                        pointBackgroundColor: 'rgba(153, 102, 255, 1)',
                        pointRadius: 6,
                        pointHoverRadius: 8,
                    }]
                },

                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'day'
                            },
                            title: {
                                display: true,
                                text: 'Date'
                            }
                        },
                        y: {
                            ticks: {
                                callback: function(value) {
                                    return levels[value] || '';
                                }
                            },
                            min: 0,
                            max: levels.length - 1,
                            title: {
                                display: true,
                                text: 'Activity Level'
                            }
                        }
                    },

                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return context.raw.label;
                                }
                            }
                        }
                    }

                }
                
            });

        } catch (error) {

            console.error("Error parsing chart data:", error);

        }

    } else {

        console.warn("Chart canvas elements not found.");

    }

});
