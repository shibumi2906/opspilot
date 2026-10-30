import {test,expect} from "../../web/e2e/test";
test("operator diagnostics shows real scoped state and trace command IDs",async({page})=>{
 await page.getByLabel("What needs attention?").fill("Status GreenShop");
 await page.getByRole("button",{name:"Start investigation",exact:true}).click();
 await expect.poll(async()=>new URL(page.url()).searchParams.get("run_id")).toBeTruthy();
 const id=new URL(page.url()).searchParams.get("run_id")!;
 await page.getByRole("button",{name:"Diagnostics",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Operator diagnostics",exact:true})).toBeVisible();
 await page.getByLabel("Diagnostic run ID").fill(id);
 await page.getByRole("button",{name:"Refresh diagnostics",exact:true}).click();
 await expect(page.getByTestId("collector-status")).toContainText("Available");
 await expect(page.getByTestId("diagnostics")).toContainText(id);
 await expect(page.getByTestId("diagnostics")).toContainText("command.process");
 await page.reload();
 await expect(page.getByRole("heading",{name:"Operator diagnostics",exact:true})).toBeVisible();
});
