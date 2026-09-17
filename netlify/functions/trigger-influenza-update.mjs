export default async () => {
  const token = process.env.GH_WORKFLOW_TOKEN;

  if (!token) {
    throw new Error("GH_WORKFLOW_TOKEN is not set");
  }

  const url =
    "https://api.github.com/repos/katsuya0505/niigata-infection-radar/actions/workflows/update-influenza.yml/dispatches";

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "niigata-infection-radar-netlify-trigger"
    },
    body: JSON.stringify({
      ref: "main"
    })
  });

  const body = await response.text();

  if (!response.ok) {
    throw new Error(
      `GitHub workflow dispatch failed: ${response.status} ${body}`
    );
  }

  console.log("GitHub influenza workflow triggered successfully.");

  return new Response("GitHub workflow triggered.", {
    status: 200
  });
};

export const config = {
  // 毎週木曜日 20:15 / 21:15 / 22:15 日本時間
  // NetlifyのcronはUTC基準
  schedule: "15 11,12,13 * * 4"
};
