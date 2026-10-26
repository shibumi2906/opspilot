import {test,expect} from "../../web/e2e/test";
test("real OIDC tenant B investigation, approval and verification remain isolated",async({page})=>{
 await page.getByLabel("Tenant",{exact:true}).selectOption("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
 await expect.poll(async()=> (await (await page.request.get("/auth/me")).json()).tenant_id).toBe("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
 await expect(page.getByLabel("What needs attention?")).toBeVisible();
 await page.getByLabel("What needs attention?").fill("Investigate GreenShop");
 await page.getByRole("button",{name:"Start investigation",exact:true}).click();
 await expect(page.getByRole("button",{name:"Approve & create ticket",exact:true})).toBeEnabled();
 const id=new URL(page.url()).searchParams.get("run_id")!;
 const pending=await (await page.request.get(`/api/v2/runs/${id}`)).json();
 expect(pending.action.arguments.customer_id).not.toBe("00000000-0000-0000-0000-000000000001");
 await page.getByRole("button",{name:"Approve & create ticket",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Ticket verified."})).toBeVisible();
 const final=await (await page.request.get(`/api/v2/runs/${id}`)).json();
 expect(final.outcome).toBe("actions_verified");
 await page.getByLabel("Tenant",{exact:true}).selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
 await expect.poll(async()=> (await (await page.request.get("/auth/me")).json()).tenant_id).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
 expect((await page.request.get(`/api/v2/runs/${id}`)).status()).toBe(404);
});
