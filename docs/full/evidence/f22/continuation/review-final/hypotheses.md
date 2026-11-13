# Гипотезы F22 для проверки

Проверьте, поддерживают ли источники формулировку и уровень уверенности. Для каждой гипотезы запишите «подтверждена как гипотеза», «нужно уточнение» или «не подтверждена» с коротким пояснением. Исходные отчёты содержат также полный список фактов и контекст прогона.

## Исходные прогоны

### F11, повтор 1 (real-r1)

[Исходный отчёт](../real-r1/real.json). Run ID: `340e7b6f-8968-4564-9f20-994989f13fcb`.

**H1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's observed Shopify order-delivery failures at 08:25, 08:40 and 08:55 UTC within the requested window. Current credential metadata explicitly reports expiration; HTTP 401 alone would not establish this cause. The exact expiration time and whether it explains every failure in the window are not established.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_9ef87921e0038c751ef90912cec6fe7e1c2a6fea9ea7932de1c1f69a8b9a32c7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_278cbfbbf51f7630aea5e307a57eccb78acf457ff108f0ca3130cc5af3645e45`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_ac6de4a1b0a77e25cb017e670f45ad25bc5632d7be8a319ad0a66c300603b11b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c6a26e35903391d4dd028d785fe42744f120f5c267466e36734c5e1e6187dbad`.

### F12, повтор 1 (real-r1)

[Исходный отчёт](../real-r1/real.json). Run ID: `29fb2e58-6b5b-4700-8f0f-83e72c7d11f6`.

**h1**, уверенность `high`

> Наиболее вероятная причина отказов доставки заказов GreenShop — истёкший credential Shopify. Гипотеза опирается на текущий статус expired и повторяющиеся HTTP 401, а не только на код ошибки или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_2e0448ee43f82ad1b3e1d4d68d7be72b29d557380d97c385881cdac943b40b4b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_77d0e8cbb5a8fa3fb3f1c1aacec4c21058c3126622915d0a82869ab83e02fc12`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_2c10051dfea2222bc05bda10e68da1b93c53f0d301228c26ee58a7b61e96f0a5`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_9aca8134e06ca1b4f173221e7b90dddedd2cbe48b586ebf9acdf38c83474f894`.

### F13, повтор 1 (real-r1)

[Исходный отчёт](../real-r1/real.json). Run ID: `5af74c90-8bc7-4c35-bf3d-00b896e67369`.

**authentication_rejection**, уверенность `medium`

> The three GreenShop delivery failures in the requested window suggest authentication rejection. The underlying cause is not established.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_373b0a62ddd15f1e690cab24c0bad1abc0f398fe4d0b4cbfc735784094c902d6`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_a855bcbf3bfde461f8db6045513250f0686b592acff707d80301196cc9984f59`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_8044b7608f0e00616f2baa5c47de466423f56ed6e7d6484b80fb269a0094a7f1`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

**credential_expiration**, уверенность `low`

> Credential expiration is a possible but unconfirmed explanation. A historical incident involved expiration, but history does not establish the present cause; HTTP 401 alone is insufficient and current credential status is unknown.

- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_a91c5213503c30ed8da6d200d908ce0aa5cf95e73a9787519e24b8734b8c0f0d`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_e60e84a8072f794b62392c4b045090e44ec3b06f09cd0306a5bab198a22d416b`.
- Необходимые проверки: credential_status_unknown.

### F15, повтор 1 (real-r1)

[Исходный отчёт](../real-r1/real.json). Run ID: `a3c1b86d-378c-44b0-89a8-33d21d6b49f4`.

**h1**, уверенность `high`

> Наиболее вероятная причина сбоев доставки заказов GreenShop — истёкший credential Shopify. Это подтверждается текущими метаданными credential и согласуется с повторными ответами HTTP 401; сам по себе HTTP 401 не доказывает истечение срока действия.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_0b8fb35ffb6eb4754964497854f0bbc8ae3ce1c40ace623b979e48c077c0bde0`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_e38615b0caa96d9c22dfa37d5097955eef9ae97d4d680234311b7c9e5fd8e15d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_515f76e41ae7d3a6dfefee5300e6df2f8c1eb662225673ca0f69e07583e8394d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_bc499b974c8a01245dc7f628f1f88dd26b01089c6c48c7b74ede52fd6f812af0`.

### F15, повтор 2 (real-r1)

[Исходный отчёт](../real-r1/real.json). Run ID: `8f3d0ade-16b5-48d4-a638-7343b4107da7`.

**h1**, уверенность `high`

> Наиболее вероятная причина отказов доставки заказов GreenShop — истёкший credential Shopify. Гипотеза опирается на текущий статус credential expired и три отказа HTTP 401, а не только на код ответа или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_14e233182b9b70ae8143b5488e87021fd082322be5b9df5e44b662cc84f88e7e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_73ca06f7f005e74126f331382ce623b302a1c75b127c770e3a6a89b316ddbc5f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_88de4505915d7b91a77a6a925d3ea6b5d906a87c672e23afe157d17f7f2fe80e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_45b4b75a4d30d5353ec35e819ed58e0f0f3b0d1b6c9e4d58e417b0cd44a5a2f0`.

### F16, повтор 1 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `701faffb-0aee-41cf-adea-983fa9b2315e`.

**h1**, уверенность `high`

> The expired Shopify credential is the likely cause of GreenShop's order-delivery failures today. Current credential metadata confirms expiration independently of the repeated HTTP 401 responses; the integration remains degraded.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_782c2be0bf85122ce0f8411ab6eb45a920ef5ec800202052a3295d39893af251`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_623b7fc848e01d1e878cb98a39ebf112bb4fcd2256e21afac505b7aaebec3a11`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_870e963140ac678f274ae39b699d8e873bb183b4cae6fef4822f405000d8658e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0a13ad5ac87e352d9ecd1d3b3466d12b3f5679807820db7abb670c67be704375`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_44e68c9f177789f0b784387181182acb3954f1d8cfefbf617a1a838df2d3ea45`.

### F17, повтор 1 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `d30cbbf2-7507-4767-88cd-e53317057e5a`.

**h_authentication**, уверенность `medium`

> Authentication rejection is a likely explanation for the observed delivery failures; the underlying cause is not established.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d62d809cab8f93a19e91dab10c6f94ae94035a926a1405c3968b38838dc11a6b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_df6decdd3112c4b3826784745ca5b3797d5d10a396fbe9006259bee2e142fe7a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_3453662bca42d5e70d70a4cd26e02d338bd2cc489043c46faaac50ce03eb76bd`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

**h_expiration**, уверенность `low`

> Credential expiration is possible but unconfirmed. Historical incidents are only precedents, and HTTP 401 alone does not establish expiration.

- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_5f6a8a2fc0415b6367911eab0efd7cd8bb6fe87410a666a661ce5b0365870eab`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_ce4e5714a1e6daf9074c130773d5baf24348691e46081ad5706cc9111930d4cf`.
- Необходимые проверки: credential_status_unknown.

### F19, повтор 1 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `a82fb721-880a-48f8-bf25-cdadf704bdac`.

**h1**, уверенность `high`

> An expired Shopify credential is the likely cause of GreenShop order delivery failures in the requested window. Current credential metadata confirms expiration, alongside three HTTP 401 delivery failures; HTTP 401 alone would not establish expiration.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_5b1e935aef536a6b74a6d6e420c8b12ba2fc505e9a4859d25bfece3d5f7dc0d5`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_f31e69985e07fee24733fe507205cad1e5b03c9826c323dbe31a2504a05a438b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0992e39c98cd880c9c0b4085c8caad57bf7017471383eb269fda42e0413dd947`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_6f7a0ff541a9b823d80e413508c9dca3260da4b36df03d0a4f939298ccc18631`.

### F19, повтор 2 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `8ea438a8-1dde-488e-8aae-f8ed8e9e50be`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's observed Shopify order-delivery failures in the requested window. Current credential metadata confirms expiration, alongside three HTTP 401 failures at 08:25, 08:40 and 08:55 UTC. HTTP 401 alone would not establish expiration; the exact expiration time and its alignment with the failures are not established.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_91321d0cdcd444644f3dff351f2174652e833a4c851d9f027707e56f3e9502c3`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d6ae2f465570cfa1ba63c5c8410923861b214fc9758e980862f3a945e1ffc23b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_594027d6202c7872b8445687e7bc710a35139236ca4a21563150460951db28fd`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_337ff2c06aa3a161233feb5973f564457dd969143299c0853edaef3a0d49fba5`.
- Необходимые проверки: Exact credential expiration time relative to the observed delivery failures..

### F19, повтор 3 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `df4c249e-7dfd-4ba7-9bca-dd0e88ecdf54`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify order-delivery failures in the requested window. Current credential metadata confirms expiration, and three delivery failures returned HTTP 401. The precise expiration time is not available, so the timing of the causal link remains unconfirmed.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_b17a7d8026a265b14020e2207a8271d023be3ccca571d6a83dd446db9d50a0d7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_b622c70a5370067db48e514fec482b2da3961506f2081cc95ee71769097a0198`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_797430dd92f6a9d8f5a4d4031156a8df0a9b0b88e220fb3c26803492a6588496`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_60a2378f81b4cdb659fa14997aca9994124b1e38fca5c02f63e19e0814203589`.
- Необходимые проверки: Confirm the credential expiration timestamp against the delivery-failure timestamps..

### F20, повтор 1 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `e9fbfa43-e1ba-4c3b-9062-9116bf152305`.

**h1**, уверенность `high`

> The expired Shopify credential is the likely cause of GreenShop's order delivery failures today. Current credential metadata confirms expiration, and three delivery failures returned HTTP 401; HTTP 401 alone would not establish expiration.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_6b5d85debfbe137c89f45f5cf28871298a714516a104c4dd032ca776a269b26c`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_60a274440cb5ae124b7fb8011cb0c00e49e9dcf520fb01319707bb01f6f4457a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_f70cc6d3a6c52cff1e454551c8f8eab64cd6e66a40b44f2f11e2aff9835c6db7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_fccbfbf4390fed74fbe49dbeac10a6b68089952607f16c6f78ec7eeeb2e56c9c`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_217886659e1ed4f7f08c81750e2a73e15c46ff7a8fe612f2f5e932901eab32be`.

### F20, повтор 2 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `b48b7508-8fa1-4f24-8206-04c5dafb749f`.

**h1**, уверенность `high`

> GreenShop's order delivery failures today are most likely caused by an expired Shopify credential. Current credential metadata confirms expiration alongside repeated HTTP 401 failures; HTTP 401 alone would not establish this cause.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_99bcf4995653a5ffc5486cdc020e2300b1619c38540e5a439b7d7aeab6de3193`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c039ba7f41daf4a34db6b5aa4f1a60efa236de472dda0384c611dc80605778cb`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_cf35454dd9d104c6cea0e6178caed12ee1181d41ab08fb3ba26c65bf32992323`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_8e8cf684dedb4fe786279e31e8db483d88c1890bdf11e95a9e713960301fbde0`.

### F20, повтор 3 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `0ec891da-a7fb-4e13-b945-5f8b3beb32cd`.

**h1**, уверенность `high`

> GreenShop's expired Shopify credential is the likely cause of today's order delivery failures. Current credential metadata confirms expiration, and three delivery failures returned HTTP 401; the causal attribution remains a hypothesis.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_2a5b6e202d0eb878bab042f4a02bdc7d3b15b8ec2f6ed990f38e62c666bff0e8`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_04337ab517d1332a1010c16bfe16d78d58a863a5b6cf75cb6f41568313c3274f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_8a49afa1eb68873be642d13dd2067d7ab82fec403300577c0f0688a41429d25f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_b9308c25ed9eb2070041123ac864d101cb9d021cbb5a592fcdb6c6ab5824baf9`.

### F21, повтор 1 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `55c043ee-fc91-4395-a329-c217b537245c`.

**h_auth**, уверенность `medium`

> Гипотеза: доставка заказов отклоняется из-за проблемы аутентификации. Истечение credential — лишь возможный вариант, не подтверждённый текущими данными. HTTP 401 и прошлые инциденты не устанавливают точную причину.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_08e690a2058ac9f93da3dcc40be565ee541adb4a719160b5d7ed82e339497f99`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_78c30cc2bf5cc2cf17f78d28d8c3f1a2503afcea0a60c218ea0e8bf7d713497d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_81899834abf78b83408964a29a36e006bcf9a7c915ee1a1ee9719c16d7099ffd`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

### F23, повтор 1 (real-r2)

[Исходный отчёт](../real-r2/real.json). Run ID: `830d1b3c-9a15-4b71-bf26-019722636980`.

**h1**, уверенность `high`

> The expired Shopify credential is the likely cause of GreenShop's delivery failures. Current credential metadata confirms expiration independently of the HTTP 401 responses; the causal link remains a hypothesis.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_05cc11b32b09c1742497f8b8cf192ba1a2f2fc728d9f1b31791b36e4900c1035`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0e20ab819a7fa68b1d3bfc47fad0919d5238897ef760e210815b9f083b2b3b4a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c97cb3248091c9f1e479b216c2b23ddd0f25b2a6ed7a0fe402ac7116e11e7d3e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_e74df07899e8c4d412172de4501d7aa5932b8becb3363c6015b0b422b8209d82`.

### F24, повтор 2 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `00120709-0d78-4f86-9dff-c9a845084094`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Это подтверждается текущими метаданными credential в сочетании с повторяющимися HTTP 401 и статусом degraded, а не только кодом HTTP или историческими инцидентами.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_522d9d25f01dc801216f2a25bad9d0a7811e49781e55b6820b2eb5699ea46785`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_115be0d4e0ab27840e16c2ce1604e70adf3a49a4aaa9a212aa7c67eaadc32a3c`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_8ec97e92189ed5e670d83247a5ed816b99065e8bdf7d633411536a9481ad48c5`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_7788232c6d7ae2c451e2c23bc1e05491ac088ea7cbd1dd2c746dde7f08059f78`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_b7806f878219491a96a409f50d89d0291713a087127f9704c9349f73609a005a`.

### F24, повтор 3 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `4e395eca-7143-4e63-b729-24dcbaef18e0`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Гипотеза опирается на текущий статус expired и ошибки HTTP 401, а не только на код ответа или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_efb6d7b41a3982a74f4781bf0369d457a8ffcbef151a3964ad17ddf84f74025c`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_3ffa5941f12a10d4ca4d4f6ef665c6e8993ed2398e58b34103bef74ffde34c15`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_695c20fd9db48229ae3de5301d633af3678ce90522385ef669a6fdf62f67b46c`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_f7879771db13ed5df8eac62e507ca4714c857fa90f72f013712c35d5d86861ce`.

### F25, повтор 1 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `dcf0c2fb-0c24-4fd8-9270-1f9d6c006284`.

**h1**, уверенность `high`

> The expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration, and three delivery failures returned HTTP 401; HTTP 401 alone would not establish expiration.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_d144dbf47a8b265f385fe08f65370869f4cce6139654e50b44df9deb8119e980`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_44e3e49a458556a5bda65ff6bec2dbb78a887176a8474e214eb5aca1c4924222`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0dfaad53c098463f7ad8061424311b7807f42b33f1a22b404ed1f75da6f0dd18`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_e2cb8d3f4fa65309015d869ed52eed412fd886e6ab3b6056ba3aa8685ab812d4`.

### F25, повтор 3 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `3808f722-6745-4376-b38b-7a05ad60735f`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata independently confirms expiration; HTTP 401 alone would not establish it. Causality remains a hypothesis.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_4b48daadbdc82d41597a123bd0cf46358fd95c13a28da11fa0507d19ced37374`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_51eef0766ffe34b48ca1d63eff5a237b0888b4c241eba06524adc700f6c91aa1`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_939719e695e3133d062a63cd6643d976aaaced4e9b561df18470a3dc65f364d5`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0c51c0e3fa28c3015265c5a11fb7e0bf828a923ca73859d9855b30dad548a379`.

### F26, повтор 1 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `b91fa31b-abc7-4fd7-92a6-0470feff24e4`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Гипотеза опирается на текущий статус credential expired и ошибки HTTP 401, а не только на код ответа или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_40a5b16f8cc0fdf0317dd6c9e8c0e5e7176f08c4a2f0635e56bdc0ed711798ca`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_b94c267930e51df8f7fc54955f0b83f0ff9d61c4c7f0e96cdcf1ace9adebd6b6`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_37630b9b36b024a760e610c4365d1ed5a737cade86253909c8e9de3c38e5674e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_beca90f7537bc8c6d6ddaebde9e04701bb6a57e0d1cf65473d6c1e4dd471805c`.

### F27, повтор 1 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `2136bfaf-f115-4577-b13e-35a668e7c597`.

**h1**, уверенность `high`

> The expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration independently of the HTTP 401 responses; the causal link remains a hypothesis.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_e18a58d6c5c3cca25e5e7fce8ef31ae0909346b565d63eb78c688bbdd5679acc`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_56e84e58d3aa5466c526aa213de33e35bff4e402b5101eaf6a6115d7e5e3f4c1`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_303bdb5e08e2359d5ad704e75f6370eeed0083ce14cd1cbf1e0398915e2f797f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_423a3174df8f08bc0c87ae098825abeca4ab863bd97ca1494da73187ee43bc72`.

### F28, повтор 1 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `1d449745-b688-458c-97c2-f961c0bb53ac`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Это гипотеза с высокой уверенностью: текущие метаданные подтверждают expired одновременно с ошибками 401 и degraded; один HTTP 401 сам по себе не доказывает истечение срока.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_f94e1681b59e914b650062e03c3dad6d853eef48e41774b2249c1b4d49763884`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_7d354d4d81bdb6fb3d65666389ae765d1214333e5888e1ec4ceb6b82e5528984`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_10789c0b7c92cda12b12a3e06b3db56520a1db57c0ca1fe7064f78ff0abd34ee`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_98ff2b354f2b4b32b6edded490a945eca5aeca364cab3f3895be53dd7d99db15`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_11f07d967555a0abc837510037f7e0725ed5f5c5498fc5ce71f0ecca23eb2070`.

### F29, повтор 1 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `56990e04-624e-43a3-8040-933832b6bebd`.

**h1**, уверенность `high`

> The expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration alongside repeated HTTP 401 failures and degraded integration status; HTTP 401 alone would not establish expiration.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_c5fd108fb07669765b9bab42b0e5a61470d7ffc56ddec0d6a2a207ed3167ed0f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_5d624c568eb0d890db1f8d3526ab58de0246aedfe6d54431fd7963eb65569939`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_045b7ed3caad67131bdbb6d95302391e0836e28e4d73463deef441611ae7715e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d32dfd3c54ebbac0be49c8e16f3c1c4dd66f40c9c532dd11695d3ebe8378a045`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_7c03388b41723ad01d0fb021a9caecb14f75bd2a7fc5f8143b6586a03d482a7e`.

### F29, повтор 2 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `996e2dcb-c404-4184-956d-123354e0be86`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration alongside repeated HTTP 401 failures; HTTP 401 alone would not establish expiration.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_99c20e72b3038b3e15cf92247414c1ec6c24a409f004537cbf452c1a2cb6d0de`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_f5f140286ea5a3c6fb81f90eeab43faeb350afe7aaffa4f79cda5c33bbd8b93e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_43e145b3516af805978e6ead623fa4a45e4c6bf61608277a06e8a3a9ffb08a8f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_054a889f3e538900dd2432c97ec3370469d8f393a0de69c07dbf59271eff0edb`.

### F29, повтор 3 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `b1a96920-cab3-49ab-820e-4d15825f7222`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration, alongside three HTTP 401 delivery failures and degraded integration status; HTTP 401 alone would not establish expiration.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_a1ae15d18dfbf882b27f5b98e5ca498d49bba64cdbf64dc9478942a45b2951e2`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_91f1dd2ef4f139269aef2dee0220dcf2c39b1b2b8e6bae81ac6db92342f5fda6`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0c0f8788039a8d6d439c1d399e7ab960095aa88d56cac043a6c5b1ff39851874`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_f2f2fdd9f453a1c37d01d5ca99437b5413aea0d36f5d90dd6fdc6d4f8845d403`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_862c3c5900d914a87a68689fbc1ec92ca70a5939272e43ef96e220ee624dfac2`.

### F30, повтор 1 (real-r3)

[Исходный отчёт](../real-r3/real.json). Run ID: `0899b472-b7fe-4cb7-b684-66b6bbf518bf`.

**h1**, уверенность `high`

> Вероятная причина сбоев доставки Shopify у GreenShop — истёкший credential. Гипотеза опирается на текущий статус credential и повторяющиеся HTTP 401, а не только на код ошибки или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_5b819b4048b7bbf5b60a33701e10ad0a5522ccdeecbdd9323c27f80fc8df16e9`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_eb508e4c3632db4f0943c25b23def68249607f60a8a3e43330f6f2aa1b79b53d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_7af31e2d63a64bf0d7a5a07152445f7068d063a1d49ed546fad9635aa622a07a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_33698e422265d26a33133da86e9bdf6b6b7baf6c21112a716750754f118c4ec3`.

### F30, повтор 3 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `0f91896f-75c9-4181-95f0-91f768a6a8bc`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Гипотеза основана на текущем статусе credential expired и трёх событиях HTTP 401, а не только на коде ответа или исторических аналогах.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_92dfd68c083bfa6f10c7f4b4159e0e98d61f974ae0d7dc6d84bcd4b37b7d8d60`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_e1f4e8e256a71035d5d879b5b134e50af78d05be4cc962a44905a2edd0929a32`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_862b4694e60bffb8fffca67b9afa9cec25184a514565b7cc4ecb95006cf4baad`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_69b429065cb1a522375dd88f5deb168f1ba4f3348e169085aebaac04e9fe76be`.

### F33, повтор 1 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `e5ef9b66-f8e1-4c93-8a1c-0abae315274c`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration, and three delivery failures returned HTTP 401; the causal attribution remains a hypothesis rather than being established by HTTP 401 or historical incidents alone.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_1feea779f3af96820c6b66e39bdac09513860937136107f39a77744bf076e5cb`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_473ef95cae4d59bca92178611952891005c8ca298300ce59be0cefc9c46085f2`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_190e29b1f1d286c7512aad8b327fc36cd10a831390e254acb119de5f24428681`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_cffb6f943630e8cf726499744d231ad691ee04be1a27a35c2e96465bd39b30b3`.

### F34, повтор 1 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `922d0f4a-5136-4550-b201-cc2fbf0924f1`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Гипотеза опирается на текущий статус credential expired и события HTTP 401, а не только на код ответа или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_305b74eea15b23921f4a0f35109e218dcbd178e61e7f2d5387e07c109410cbdf`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_a819a0e253dc2fd1fd6797408a25826a4cd3149d39befd2202d821adbae07b5a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_196bee5d8f5acab8ab552d848484c17b6f0113c87e334511ff2fa30652a60eb4`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_88e9ebd1bde8c4540259dc4ff7cd43fb553259fa928dd28f031cc83dbf169bd5`.

### F34, повтор 2 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `447aef14-36d3-43e0-8c78-bd56c06cbc4d`.

**h1**, уверенность `high`

> Гипотеза: сбои доставки Shopify у GreenShop вызваны истёкшим credential. Текущие метаданные подтверждают expired, а события фиксируют HTTP 401; один лишь HTTP 401 и исторические инциденты не доказывают текущую причину.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_6161b4805e64cca80ffe1ea06ee4ce82a677cd7797a74440fd766db183dd3669`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_21cc0924be5a007dfa5f5aad1497ddbba501e5ce5b47fb011030b0d389470b01`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0ac252d5a2367af8280f92410a7c9d85124b3dc23c830b11368ec67a44acb2b2`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_55b9629eaae9cf22602ba656bc097f307ccaa575859267277b0246e300cbc452`.

### F34, повтор 3 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `1565b832-02b2-4ac7-8a0d-fdb9f486f670`.

**h1**, уверенность `high`

> Вероятная причина отказов доставки Shopify у GreenShop — истёкший credential. Гипотеза опирается на текущий статус credential expired и повторяющиеся HTTP 401, а не только на код ошибки или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_e716b7ee89ebdeb2de3f1f347c9e4f72a8f6a3372c7bd699f2d8ce466761502e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0f43bfd912d1d024e458e06d93defc5d80079a18758f087cb78507d34ab41e5b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_6aba64f5fc723782a35ce42b18fb3db7fce77ae943f27d304cf4c29c5b484f9b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c0d48eaa6c6fbbbcdfc524eca4670143191b7b6eef43066c431fb4262616695f`.

### F35, повтор 1 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `516871fc-6af9-40ec-b59f-213dc3b90670`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify order-delivery failures during the investigated window. Current credential metadata confirms expiration; HTTP 401 alone would not establish this cause.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_b3ad18f1e8576efcfcf88dbcd10e8a0c026a8b66db41035bd2b7ad1d7bd94773`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_32a556a871265a85168496fcea281b151e2df6fb998b94f83f8eac23b9b425f6`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_3e5c4441e0432fcd99e650c113dd6b2b3c6f3e633d36e9c40eeacfbd52ec9e94`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_eaee105b11193ac8b3cfda55f5df0d7961b76361031c662e32b652d0217a11a7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_a45660336aaf51a6a9aac37542907d679f46b36c9368a35fd2030693a7285297`.

### F35, повтор 2 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `8e427321-1c85-483b-9ae6-8d8bf2608f12`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify order-delivery failures. Current credential metadata independently confirms expiration; the HTTP 401 events alone would not establish this cause.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_cfef47b5fdb001374325a48015fbedbd2f292c3bfcca4c09e87884b690928b15`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_a28f8bb026eeb2915d48e87438202f2cea82a07cf588a6af23e2645ab787f7dc`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_8cd060f7423ca82e2004900ddcf1efee809cc96697bce252153d7fe41b33994f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c13c1b26e7cf4368a0f47706d8b19b0113fb5dfbbe7c68858fe801c963c07a3b`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_459f68ff5c50b429ee30f44b86ca538b9c0f8cc0a7d502f5850684fa502cab97`.

### F35, повтор 3 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `5c008d82-cbf3-40e9-bb2f-09b0daeb3b34`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify order delivery failures in the investigated window. Current credential metadata confirms expiration independently of the HTTP 401 responses; causation remains a hypothesis.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_e3cba1ad1b8916ef1757a9d601dec06a7e62e368c5f90ccce81b5c8ed0e4b446`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_a1ac7bc64b252f0f85e3adfcfa0baeafcbb0bc99ab66bfcb6f92066407007cf5`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_4302285ad4f528f3e6b6a32efcd62d73c8dadfad1ad1f631e81bdb7577ddee05`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_115a597868306d1b002e99fc416d58f32f8f8533b64a93742aa883e076361f46`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_245ee2674ec3010e58d653d76c6496629fb9c794368950377361d379c3061f71`.

### F36, повтор 1 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `c4f73cde-70d1-467d-8f77-e1035b6b256d`.

**h1**, уверенность `high`

> The expired credential is the likely cause of GreenShop's Shopify authentication failures. Current credential metadata independently confirms expiration; HTTP 401 responses alone and historical incidents do not establish the cause.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_5419a1b47e3aaa6647ed54e72bf0b469e7fad86cf04b09892b0ef33006983308`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_4fe23fc789c121c9494164b4654abb4a9da640111f7e04e553190b34f9bec6b3`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_67f1f017b8b81979c432c939c16f0188c28e08837d98201e0aa07379dac5039e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_bb47fdee44e3c2bab9e9ae79ebd83d58f19269fbac6bd71cbc1a4379ce2e16be`.
- Поддерживает: `integration_status` — {"status": "degraded", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_781c5a709a97f9413277a6390e12050cc6c30b38c48ebad21da27cfccbd6ec79`.

### F37, повтор 1 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `4a41dcbb-8a37-4492-97d3-b2fb2199d066`.

**H1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration, and three delivery events show HTTP 401; the causal link remains a hypothesis rather than being established by HTTP 401 or historical incidents alone.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_8deebf6a0951ea510565206b43a91a7dba657ca11290d1a0760e35ecb152e036`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_6d1077d1dce872ede8f6aef97d9126a69efa65a9c175bdda4940fe65c3177a06`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_58d9936061d9d10ec5ae641893e9b59449c8a449075e8569a3d419035f35c24a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_9265e9dd7fe2dbff5da8eeef56431e47c549169ef0f54014e4c6323afd06fa10`.

### F38, повтор 1 (real-r4)

[Исходный отчёт](../real-r4/real.json). Run ID: `74469811-a439-4596-adae-6b986685034e`.

**H1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration independently of the HTTP 401 responses, although the causal link is not directly verified.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_c62927cfa0508f0cee4ad1a87375c35bdf846231a22150c319d96763fa8a9154`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_b7cf2171ed907f19174ba93e2cc49d1a87e4d94ca76fbbb0d61cbf827c46c69a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_42a37c178e4888fbd7cb67bb69fc20679941b6c0016063aefb0bbb7195f2b8d5`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_a7570e433c08dd7938a15caeba6ba88804d780141795b5e07da1c51764fd444b`.

### F47, повтор 1 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `3d42ec82-ef0b-4c10-8d7a-81d0d830e897`.

**h1**, уверенность `medium`

> An authentication or authorization issue may explain the delivery rejections. The precise cause is unconfirmed; HTTP 401 alone does not establish credential expiration.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_303f75a0be384623988fb2f2dcdc1c13b2d6b79f508394e750fb050cfb454978`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_ce31c901222ee92242b94058582b26d0a7d17c517fe39c2e1220846dd328f39d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_141fe195df1a9ab5f0acdcd51b3689303a77a5129babb384aa9af65c23237abc`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

**h2**, уверенность `low`

> Credential expiration is a possible but unconfirmed explanation. Similar historical incidents are not proof of the present cause, and current credential metadata is unknown.

- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_4ec2969d799d4cedef9e47dce465163cc226175cf9155a90561e0da26038c8a8`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_f2f77d33d8724c54bba686d8ce643981eae89592f3525fe96c4300d66fdd969d`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

### F50, повтор 1 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `fa34e3f9-4d54-43d7-8f55-07ab7a6accd7`.

**h1**, уверенность `low`

> Гипотеза: отказы доставки связаны с проблемой авторизации; истечение credential — лишь возможная причина. HTTP 401 и похожие исторические инциденты не подтверждают истечение сейчас. При неизвестных статусах интеграции и credential текущая причина не установлена.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_a642124b4830c39251bb5cd7a27f5c3f3046f9ab11d1f30c98f0b48636a8ab5c`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_9a97ca7d4f1163fbbccc62630c62893190de458d481531f3cad59c9742b1aab1`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_437283ba63700f0a387dbf7d59374a773271d2754ed9972cdaf468cbb672c529`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

### F50, повтор 2 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `7f9450fe-c75b-4695-9ce9-d2e8d8dd4ccb`.

**h1**, уверенность `low`

> Возможна проблема авторизации доставки Shopify. Истечение credential — лишь один из вариантов: HTTP 401 и исторический инцидент не подтверждают текущую причину; статусы интеграции и credential неизвестны.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_42986bb92d2ff38db75331b1913d5c56608a1e79354957076013524414d8ec7a`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_a0b52f4483c0dc6c2f179fe9aacb116d22c29cdd9f7cfbc5278ffc216d42ab5d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_1538c147ccef34b6ee291ed8d5d4b66fef4cbe610d0cf41a5172f958c9692c52`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.

## Диагностические повторы

### F25, повтор 2 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `59a80296-e9e7-4032-bca1-2f4208b1d512`.

**h1**, уверенность `high`

> An expired credential is the likely cause of GreenShop's Shopify delivery failures. Current credential metadata confirms expiration, and three delivery failures returned HTTP 401; the causal attribution remains a hypothesis rather than proof from HTTP 401 or historical incidents alone.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_2d510ee886f559c83ac9e7d6c429bf86275ce67a5569c2effe259e196f55f13f`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_e56421b07601ac32046eb6d9e5b288b0c632175a47b2d4e7909c6fdbb8f6f839`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_3a2fe00edda80e5b1c79f03f9b5a417680c89b3d8f75adca0be49ab68fcb39fd`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0f7726bb085c0af16c5eedd6206a9eda87b447d3cbd001124e19d4f80a567a0a`.

### F24, повтор 1 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `dd1418c7-994a-46e7-ae22-e595f2e88e4b`.

**h1**, уверенность `high`

> Вероятная причина сбоев доставки Shopify у GreenShop — истёкший credential. Его текущий статус expired подтверждён метаданными, а ошибки 401 согласуются с этой гипотезой. Сами по себе 401 и исторические инциденты не доказывают текущую причину.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_b622eb9f53eda989a24c168afb173cdbdcd600ec32e79f1e4fae18fcdf5087dd`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_3ad154102159295c3773db74a15a5b832a1ce95ecb5cec224203240bca5d8882`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_2cf0694b7c62ed35a29a47be6c30d3c73c9648c19a771d619c5cf71e9f634551`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_abfc1b183f9dcd522970ed50ab508d5680b4f9594d1ac409103e6daf027b7415`.

### F30, повтор 2 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `7ddd4121-3573-4442-bc86-70dfc910f25d`.

**h1**, уверенность `high`

> Вероятная причина сбоев доставки Shopify у GreenShop — истёкший credential. Гипотеза опирается на текущий статус credential expired и повторяющиеся HTTP 401, а не только на код ответа или исторические инциденты.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_76592fd86a312f739522c7db218b0ce204cc191955c59e5fb8381ea7dc56172d`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d8d58969e6eccedbf3cfaff124b16d52a79c00dc56b52bb5b98681ed2521d7e7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_71f49889f85c0d25eb03efe4c92c3ed39f6182ae976c36054f5afcefb5a0ad06`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_28aa1194519ce17cf7a204852d6ac166306a0ecd15513956997fa495a65a03d5`.

### F15, повтор 3 (real-r5)

[Исходный отчёт](../real-r5/real.json). Run ID: `d05da70f-6fcd-4cbd-92b0-36fd78a310ee`.

**h1**, уверенность `high`

> Наиболее вероятная причина сбоев доставки заказов GreenShop — истёкший credential Shopify. Текущие метаданные подтверждают expired, а три события доставки показывают HTTP 401. Сам по себе HTTP 401 не доказывает истечение credential; исторические инциденты не являются доказательством текущей причины.

- Поддерживает: `credential_status` — {"status": "expired", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_1cacb0cc27852fdcbc31dcc8bfbd4b061f12350f45ec13519a61a2d860766118`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_89252d7d41fcc70694340287452eb049d021d9fca09fb1fbb1b379b134faa4fb`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_7da27b877ed2a8b2476d5cbd0e93eed842c00ea08cd3422803d893a431d9f424`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d636b2c7b8ee7c350a97f9bf66528ca237158528a411e8648f5d7af4da6c1cef`.

### F18, повтор 1 (real-r6)

[Исходный отчёт](../real-r6/real.json). Run ID: `de0c3914-1f69-4c34-9cff-7bef6afb299c`.

**h1**, уверенность `medium`

> Гипотеза: доставка заказов отклоняется из-за проблемы авторизации. Точная причина не установлена: ошибки HTTP 401 противоречат общей оценке healthy при действующем credential.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_6bd01d2acc869f47691ca49de245628928950fe454a50cc5ede24ba806930ec1`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_95eddb3872caf60573810f86f14670ab8f2e2bdde87e48bf7fed507793392773`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_ebe4d3b1831140b79630162eaaee421316f48f84f1cafbbdbbff03f2ed550f49`.
- Противоречит: `integration_status` — {"status": "healthy", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_d30e8821c8e5d381b1f2f42f2a36249a4877faf507e305de0514067fbd763057`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_29a55af58ffdf36697bc874873ce350b6dcb694e71665988508ad192d1e917c5`.
- Необходимые проверки: contradictory_observations.

**h2**, уверенность `low`

> Гипотеза об истечении credential не подтверждена. Исторические случаи не доказывают текущую причину, а HTTP 401 сам по себе не означает истечение срока.

- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_934546c9bf2681a993d0b4b8c2d1f2231721fc385de0db90ba4abf329f88484a`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_d8435da4ef2e4d5ad91fd60389bcc0959343b27dfb50e0c16b621576144e7837`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_29a55af58ffdf36697bc874873ce350b6dcb694e71665988508ad192d1e917c5`.
- Необходимые проверки: contradictory_observations.

### F22, повтор 1 (real-r6)

[Исходный отчёт](../real-r6/real.json). Run ID: `9c3b3b0a-bfbd-4708-959c-1c419aca6b27`.

**h_auth_rejection**, уверенность `medium`

> An authentication or authorization problem may explain GreenShop's delivery failures. Three HTTP 401 events occurred despite healthy integration status and valid credential metadata; the underlying cause remains unconfirmed.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_7ac39a0a6fa1f05b1ca3d1fd068a74825983520d4a3130c8160a6fd38e9cf7a7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_10f3776b1046ad5334d3c8d1a20949c432ddab26efecffa98677c5843b423649`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c45c6808b6be0e795eeb83688ac8351ea843c0eaadd25f5d4f117d402e19b045`.
- Противоречит: `integration_status` — {"status": "healthy", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_5070d452d937340386d2d04243b2b4505090230491e902622f9ee373cba2fa77`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_d71a4d01fff67643d33ef069e0999c852bd035bc9cfce573e557e864ddb0c865`.
- Необходимые проверки: Reconcile healthy integration status and valid credential metadata with the failed deliveries.; Inspect sanitized rejection details and verify which credential and permissions the failed deliveries used..

**h_expired_credential**, уверенность `low`

> Credential expiration is a low-confidence historical analogy, not a confirmed present cause. Current credential metadata reports valid, and HTTP 401 alone does not establish expiration.

- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_4ad901686f1452f9a0e6e863d7964bc227a4fe4f5408dbd934ac29b83e6089f0`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_15d1a6cb87a7ba5aa3f4f77c6c06d0df2019077377900edd738c1a78c47bbfa3`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_d71a4d01fff67643d33ef069e0999c852bd035bc9cfce573e557e864ddb0c865`.
- Необходимые проверки: Verify that valid credential metadata applies to the credential used by the failed deliveries..

### F14, повтор 1 (real-r7)

[Исходный отчёт](../real-r7/real.json). Run ID: `511306b9-05dd-4ab6-b0b1-597738a2af4e`.

**H1**, уверенность `medium`

> An authentication or authorization issue may explain the delivery failures, but its specific cause is unconfirmed. Healthy integration status and valid credential metadata do not explain the repeated HTTP 401 responses.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_4d7ac154a5a273f035f66b0cee97f7a022139c99a83d0f84115a8e219ab5054e`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d241855a54f6691fd760f3738cb93d58cabc238dcc7827010a244d77defabdd7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_d8bc07c47f7977aced97ecd082273a5bb55f700faa4a31bbb68bb16a1a538197`.
- Противоречит: `integration_status` — {"status": "healthy", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_bd658845ce3e4d2da290687639a160c93e8bee8b51febb230c9225ac3caf23d6`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_809e5e3e908c738f9ff2d928092b2cd3a7acb97d6277533eda5c300362685c78`.
- Необходимые проверки: contradictory_observations; Inspect rejection details and verify whether credential metadata and delivery requests refer to the same credential and endpoint..

**H2**, уверенность `low`

> Credential expiration is a historical explanation, not an established present cause. Current metadata reports a valid credential; HTTP 401 alone does not establish expiration.

- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_e49bb8c37ecf089b0ff09cbb7f82de076ef47b833ce31416ed08ecdded926b34`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_b3c41804c8072c34c6641a5d8245de389253f45c28a834cf50bcbb7273d5c413`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_809e5e3e908c738f9ff2d928092b2cd3a7acb97d6277533eda5c300362685c78`.
- Необходимые проверки: Reconcile valid credential metadata with the authentication rejections before attributing failures to expiration..

### F14, повтор 2 (real-r7)

[Исходный отчёт](../real-r7/real.json). Run ID: `e86cf00a-703c-404a-9073-0de9c74da791`.

**h1**, уверенность `medium`

> Order delivery may have an authentication-path issue despite healthy integration status and valid credential metadata. The specific cause is unconfirmed; HTTP 401 does not establish credential expiration.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_62ddd31ba9c9635d5e3f691a4add2cdc933b2632060482e5f1eb64878a166ca7`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_100ff9b9fd077f803e15d94ebc500c738af83ddac6422e9b14f20b8dddd799cd`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_68a1c6be2b6ee55d7a0abe798e98d66944b778df0a096357478e8a26c04c7b0f`.
- Противоречит: `integration_status` — {"status": "healthy", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_5f2100036232a017d2a2dd1bb3d849b8c42a13342f941b202644e4b1ee8d4af6`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_fd5ff0cc56bf1b70d4ed6c7a44816d40cbd9e12094b7dbf0458036e44ec670a3`.
- Необходимые проверки: Reconcile healthy status and valid credential metadata with repeated delivery rejections.; Inspect rejection details and confirm which credential and destination were used by failed deliveries..

### F14, повтор 3 (real-r7)

[Исходный отчёт](../real-r7/real.json). Run ID: `9a5264ab-a7d9-4b14-9888-1a04f5bced7b`.

**authentication_rejection**, уверенность `medium`

> Order deliveries may be failing because of an authentication rejection. Three HTTP 401 events support this, but the specific cause remains unconfirmed: current monitoring reports healthy status and valid credentials.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_f7576157b901acc920380481b367ad41bc5054d54289343e24d8e512e6975d01`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_3bac9103c98827e21ddf653a66f61a29bf799a54a3ff743931800e1080462a73`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_0f733ca236af6f0a12d8b10ede00d343a8f59130b5b971ef077ebde153fe611c`.
- Противоречит: `integration_status` — {"status": "healthy", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_db33fe56b4fd8318e3f92e02d2f0ee00c414827dcab60e2816adbb790029b688`.
- Противоречит: `credential_status` — {"status": "valid", "checked_at": "2026-10-18T09:00:00Z"}. ID `ev_87defcfb83845ee6a9b108a0ca7b30c1fee4c4567d4c4caa5dcfe8b392af09f2`.
- Необходимые проверки: Reconcile healthy integration and valid credential observations with the failed deliveries; inspect rejection details and whether credential validation covers the delivery authentication path..

### F50, повтор 3 (real-r7)

[Исходный отчёт](../real-r7/real.json). Run ID: `485e1b28-5612-4703-a27b-57b91860d5a3`.

**h1**, уверенность `low`

> Гипотеза: отказы доставки могут быть связаны с истечением credential. Причина не установлена: HTTP 401 и сходные исторические инциденты не доказывают истечение сейчас, а текущий статус credential неизвестен.

- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:55:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_705ef560e70b88680981b49e31762ca0a7d845fc0cbdda5b395c1828d53b6e61`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:40:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_53e365539ec3ff18dc803c2b81d10ccf9766d101a98fd62c74d76825b3bd12fd`.
- Поддерживает: `integration_event` — {"http_status": 401, "occurred_at": "2026-10-18T08:25:00Z", "summary": "Synthetic delivery rejected"}. ID `ev_c556f560042069e115f4713f7af9ac55b8ac108906818ef23183cc62e13ba6b4`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-15T09:00:00Z", "summary": "Заказы Shopify не приходят, HTTP 401", "root_cause": "Истёк срок credential"}. ID `ev_3b4b4d8af75b02a800934c9e3ba6ede13d57b8b1868c477e08df44905ad31984`.
- Поддерживает: `incident` — {"occurred_at": "2026-10-12T09:00:00Z", "summary": "Shopify delivery failed with HTTP 401", "root_cause": "Expired credential"}. ID `ev_c065651dc06f73e4e07d98d77cd893cee5b3cec763f4c9ff047583dc9c4b3853`.
- Необходимые проверки: credential_status_unknown; service_status_unknown.
