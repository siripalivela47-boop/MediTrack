document.addEventListener('DOMContentLoaded', () => {
  if (!window.Chart || !window.dashboardData) return;
  const d = window.dashboardData;
  const movement = document.getElementById('movementChart');
  if (movement) new Chart(movement, {type:'line',data:{labels:d.labels,datasets:[
    {label:'Received',data:d.received,borderColor:'#147dff',backgroundColor:'rgba(20,125,255,.10)',fill:true,tension:.35,pointRadius:3,borderWidth:2},
    {label:'Issued',data:d.issued,borderColor:'#20b8a6',backgroundColor:'rgba(32,184,166,.08)',fill:true,tension:.35,pointRadius:3,borderWidth:2}
  ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top',align:'end',labels:{usePointStyle:true,boxWidth:7,color:'#425574',font:{family:'Inter',size:11}}}},scales:{y:{beginAtZero:true,grid:{color:'#edf1f7'},ticks:{color:'#6d7c95'}},x:{grid:{color:'#f4f6fa'},ticks:{color:'#6d7c95'}}}}});
  const category = document.getElementById('categoryChart');
  if (category) new Chart(category,{type:'doughnut',data:{labels:d.categoryLabels,datasets:[{data:d.categoryValues,backgroundColor:['#147dff','#20b8a6','#ff9b42','#8b5cf6','#f4c64e','#5272a7','#ef6470'],borderWidth:3,borderColor:'#fff',hoverOffset:5}]},options:{responsive:true,maintainAspectRatio:false,cutout:'68%',plugins:{legend:{display:false}}}});
});
