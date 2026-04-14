# API 密钥与凭证说明

本文档解释你 `.env.local` 中所有凭证的用途，以及自动交易项目对它们的需求状态。

---

## 你拥有的凭证一览

### ✅ 必需 — CLOB 开发者凭证（下单必须）

你在 Polymarket 后台创建的"开发者码"，用于向 CLOB（中央限价订单簿）提交订单。

| 字段 | 你的值 | 用途 | 对应 .env 变量 |
|------|--------|------|----------------|
| **API 使用地址** | `0xb6096926...8d130` | CLOB API 用的签名地址，**不是钱包地址**，不要往这里转钱 | `POLYMARKET_WALLET_ADDRESS`（用于 API 签名） |
| **apiKey** | `019d856d-3b8b-795b-...` | CLOB API 认证密钥 | `POLYMARKET_API_KEY` |
| **secret** | `dCiwsJU-FVjB-Gdtwha...` | HMAC 签名密钥（Base64 编码） | `POLYMARKET_API_SECRET` |
| **passphrase** | `0405a1301d32...` | API 认证口令 | `POLYMARKET_API_PASSPHRASE` |

> ⚠️ 以上四个值是**手动管理 API 凭证**的方式。如果使用官方 `py-clob-client` SDK，SDK 可以用私钥自动 `create_or_derive_api_creds()`，但你已经有手动创建的凭证，也可以直接用。

---

### ✅ 必需 — 私钥（签名交易必须）

| 字段 | 你的值 | 用途 | 对应 .env 变量 |
|------|--------|------|----------------|
| **phantom钱包私钥** | `0x56d778a32a44...` | EVM 钱包私钥，用于 SDK 签名订单（EIP-712） | `POLYMARKET_PRIVATE_KEY` |

> ⚠️ 这个私钥是你最重要的凭证。SDK 用它来签名下单请求。**绝对不要泄露**。

---

### ✅ 必需 — 充值钱包地址

| 字段 | 你的值 | 用途 |
|------|--------|------|
| **polymarket充值钱包** | `0xebB80D98Ba64...bfa9` | 你的 Polymarket **资金钱包**（funder address），USDC.e 余额在这个地址上 |

> 💡 这个地址是 SDK 初始化时的 `funder` 参数。如果你是通过 Polymarket 网站注册的（Email/社交登录），你的钱包类型是 **Proxy Wallet（签名类型 1 或 2）**，`funder` 地址就是这个充值钱包。

---

### ⚠️ 可选 — Relayer API 密钥

| 字段 | 你的值 | 用途 |
|------|--------|------|
| **Relayer API Key** | `019d84c0-e06c-7eff-...` | 用于链上免 gas 操作（redeem、split、merge 等） |
| **签名者地址** | `0x0DD0e421a9...CEfd8E` | Relayer 请求的签名地址 |

> 💡 Relayer 用于免 gas 的链上操作（比如结算后 redeem token）。**下单本身不需要 Relayer**，CLOB 下单已经是免 gas 的。初期可以不配。

---

### ❌ 不需要 — Solana 地址

| 字段 | 你的值 | 用途 |
|------|--------|------|
| **phantom钱包sol地址** | `39S8i3YzH3EM...` | Solana 链地址 |

> Polymarket 运行在 **Polygon 链**上，Solana 地址完全用不到。忽略即可。

---

## 你的钱包类型判断

根据你拥有的凭证分析：

- 你有 `CLOB API Key / Secret / Passphrase`（手动创建的）
- 你有一个私钥（`0x56d778...`）
- 你有一个独立的"充值钱包"地址（`0xebB80D98...`）

**判断**：你很可能是 **Proxy Wallet** 用户（通过 Polymarket 网站注册），因为：
1. API 使用地址（`0xb609...`）和充值钱包地址（`0xebB8...`）不同
2. Proxy Wallet 是 Polymarket 为 Email/社交登录创建的合约钱包

对于 Proxy Wallet：
- SDK 的 `signature_type` 应该设为 `1`（不是默认的 `0`）
- `funder` 应该设为充值钱包地址 `0xebB80D98Ba64ED39b0de71ceE18E101Ddbb6bfa9`
- `key` 设为你的私钥

---

## 最终 .env 配置映射

```bash
# === CLOB 认证（已有手动凭证，可直接用） ===
POLYMARKET_API_KEY=019d856d-3b8b-795b-b36f-7f72ef490414
POLYMARKET_API_SECRET=dCiwsJU-FVjB-Gdtwha_jQF8jnreTC5uLk0_oKdccxk=
POLYMARKET_API_PASSPHRASE=0405a1301d32101ce89f7d82bf6c98b51fa16818c7b16e21ecf66883ab3f36c2

# === 私钥和钱包地址 ===
POLYMARKET_PRIVATE_KEY=0x56d778a32a4413fa098ab223e46725e2561330443f509643723aec76db6632e1
POLYMARKET_WALLET_ADDRESS=0xb6096926c21e95323f827e53d1b6292ec2a8d130
POLYMARKET_FUNDER_ADDRESS=0xebB80D98Ba64ED39b0de71ceE18E101Ddbb6bfa9

# === 签名类型（Proxy Wallet = 1） ===
POLYMARKET_SIGNATURE_TYPE=1

# === Relayer（可选，暂时不用） ===
# RELAYER_API_KEY=019d84c0-e06c-7eff-b381-53743cb44bf4
```

> ⚠️ **安全提醒**：不要把 `.env` 提交到 Git。已在 `.gitignore` 中配置了 `.env*` 规则。
