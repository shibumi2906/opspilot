import {test,expect} from "../../web/e2e/test";

test("durable usage survives refresh; unknown cost never renders as zero",async({page})=>{
 await page.getByLabel("What needs attention?").fill("Status GreenShop");
 await page.getByRole("button",{name:"Start investigation",exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get("run_id")).not.toBeNull();
 const id=new URL(page.url()).searchParams.get("run_id")!;
 await expect.poll(async()=> (await (await page.request.get(`/api/v2/runs/${id}`)).json()).status).toBe("completed");
 await expect(page.getByTestId("model-cost")).toHaveText("0.000000");
 const before=await (await page.request.get(`/api/v2/runs/${id}`)).json();
 expect(before.usage.llm_calls).toBeGreaterThan(0);
 expect(before.usage.cost_status).toBe("known");
 expect(before.usage.cost_usd).toBe(0);
 expect(before.usage.cached_input_tokens).toBe(0);
 await page.reload();
 await expect(page.getByTestId("model-cost")).toHaveText("0.000000");
 const after=await (await page.request.get(`/api/v2/runs/${id}`)).json();
 expect(after.usage.llm_calls).toBe(before.usage.llm_calls);
 expect(after.usage.read_calls).toBe(before.usage.read_calls);
 // Response-boundary fixture only; actual unknown transport/crash reservations use PostgreSQL tests.
 await page.route(`**/api/v2/runs/${id}`,async route=>{
  const response=await route.fetch(),body=await response.json();
  body.usage={...body.usage,input_tokens:null,output_tokens:null,cost_usd:null,
   cost_status:"partial",unknown_usage_count:2,reserved_tokens:16000};
  await route.fulfill({response,json:body});
 });
 await page.reload();
 await expect(page.getByTestId("model-cost")).toHaveText("Unknown / partial");
});
