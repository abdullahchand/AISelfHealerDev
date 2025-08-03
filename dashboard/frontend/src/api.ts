export async function fetchWorkers() {
  const res = await fetch('http://localhost:8081/api/workers');
  return res.json();
}

export async function fetchWorkerDetail(workerId: string) {
  const res = await fetch(`http://localhost:8081/api/worker/${workerId}`);
  return res.json();
}