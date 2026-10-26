import pg from "pg";
const databaseUrl = process.env.E2E_DATABASE_URL;
export async function ticketCount(actionId?: string): Promise<number> {
  if (!databaseUrl || new URL(databaseUrl).pathname !== "/opspilot_full_test")
    throw new Error(
      "Browser tests require E2E_DATABASE_URL for the isolated opspilot_full_test database.",
    );
  const client = new pg.Client({ connectionString: databaseUrl });
  try {
    await client.connect();
    const identity = await client.query("SELECT current_database() AS name");
    if (identity.rows[0].name !== "opspilot_full_test")
      throw new Error("Connected database is not opspilot_full_test");
    const result = await client.query(
      actionId
        ? "SELECT count(*) FROM domain.tickets WHERE originating_action_id=$1"
        : "SELECT count(*) FROM domain.tickets",
      actionId ? [actionId] : [],
    );
    return Number(result.rows[0].count);
  } finally {
    await client.end();
  }
}
