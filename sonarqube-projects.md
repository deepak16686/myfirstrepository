# SonarQube Projects - Legacy Modernization Platform

**SonarQube URL:** http://localhost:9002
**Username:** admin
**Password:** N7@qL9!fR2#XwA8$

---

## Project Details

### Legacy-Banking-Core
- **Project Key:** `legacy-banking-core`
- **Description:** Legacy mainframe banking system
- **Token:** `squ_e6beb92fd1fadb7a83864325012ed5ad0c12afd8`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-banking-core

### Legacy-Insurance-Policy
- **Project Key:** `legacy-insurance-policy`
- **Description:** Old insurance policy management
- **Token:** `squ_ba40d5b4ed7e0dc2d7a682a3dcf3181cde28a126`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-insurance-policy

### Legacy-Retail-POS
- **Project Key:** `legacy-retail-pos`
- **Description:** Point of sale system from 2005
- **Token:** `squ_912f78003468604834815bdd649a79e43e1c4784`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-retail-pos

### Legacy-Healthcare-Records
- **Project Key:** `legacy-healthcare-records`
- **Description:** Patient records system
- **Token:** `squ_7dcf991c72a02715e6b9c632a6d8f8c30130d6b3`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-healthcare-records

### Legacy-CRM-System
- **Project Key:** `legacy-crm-system`
- **Description:** Customer relationship management
- **Token:** `squ_31467c71462fb2da38438faec77dea194c9a3f7a`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-crm-system

### Legacy-ERP-Finance
- **Project Key:** `legacy-erp-finance`
- **Description:** Financial ERP modules
- **Token:** `squ_08900fea5aaca910b46dbb98b9754169550bfeeb`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-erp-finance

### Legacy-Inventory-Manager
- **Project Key:** `legacy-inventory-manager`
- **Description:** Warehouse inventory system
- **Token:** `squ_92654f6de8a660fe153fe3f822b5f0ba173f0f9f`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-inventory-manager

### Legacy-HR-Payroll
- **Project Key:** `legacy-hr-payroll`
- **Description:** Payroll processing system
- **Token:** `squ_9134e9506ae44b516a24b67cdfa5022ba82325ac`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-hr-payroll

### Legacy-Telecom-Billing
- **Project Key:** `legacy-telecom-billing`
- **Description:** Telecom billing platform
- **Token:** `squ_46eaf8380e92290efa4a58e69d16d198152ccee1`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-telecom-billing

### Legacy-Logistics-Tracker
- **Project Key:** `legacy-logistics-tracker`
- **Description:** Shipment tracking system
- **Token:** `squ_d34e75610d1b2107eac063c2ea7ec961b63f7792`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-logistics-tracker

### Legacy-Hotel-Booking
- **Project Key:** `legacy-hotel-booking`
- **Description:** Hotel reservation system
- **Token:** `squ_7c898bb6903739eae91befb02d1b27ad0255729a`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-hotel-booking

### Legacy-Flight-Reservation
- **Project Key:** `legacy-flight-reservation`
- **Description:** Airline booking platform
- **Token:** `squ_7684e45c21d7c138a34a3e812f73d8c160687817`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-flight-reservation

### Legacy-Supply-Chain
- **Project Key:** `legacy-supply-chain`
- **Description:** Supply chain management
- **Token:** `squ_869ebe60e3c88b2379556d8dabbe6c0605e38dd7`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-supply-chain

### Legacy-Manufacturing-MES
- **Project Key:** `legacy-manufacturing-mes`
- **Description:** Manufacturing execution system
- **Token:** `squ_1f86b2c63b0353d45786f7aa9464ddd25ef2b229`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-manufacturing-mes

### Legacy-Asset-Management
- **Project Key:** `legacy-asset-management`
- **Description:** Asset tracking system
- **Token:** `squ_8947b70105b801e45fc5946d1caae6316201d117`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-asset-management

### Legacy-Document-Archive
- **Project Key:** `legacy-document-archive`
- **Description:** Document management system
- **Token:** `squ_8fc572dfca98bd7d3f18afdd5efe05917fec904d`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-document-archive

### Legacy-Email-Gateway
- **Project Key:** `legacy-email-gateway`
- **Description:** Email processing gateway
- **Token:** `squ_797b5167c2f04d74ba9ac532648d98f229601ee2`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-email-gateway

### Legacy-Reporting-Engine
- **Project Key:** `legacy-reporting-engine`
- **Description:** Business intelligence reports
- **Token:** `squ_1734ffc50a1ea2673bd752613bc28c07acaca050`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-reporting-engine

### Legacy-Authentication-Service
- **Project Key:** `legacy-authentication-service`
- **Description:** User authentication system
- **Token:** `squ_b07ebe25fd436890a9a1df87e3978732f239274c`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-authentication-service

### Legacy-Data-Warehouse
- **Project Key:** `legacy-data-warehouse`
- **Description:** Data warehouse ETL system
- **Token:** `squ_069323f75404f7756ac0e1f20ad133da02a59f7e`
- **Dashboard:** http://localhost:9002/dashboard?id=legacy-data-warehouse

---

## Quick Access Commands
```powershell
# Analyze a project with Maven
mvn sonar:sonar \
  -Dsonar.projectKey=<project-key> \
  -Dsonar.host.url=http://localhost:9002 \
  -Dsonar.login=<token>

# Analyze with SonarScanner CLI
sonar-scanner \
  -Dsonar.projectKey=<project-key> \
  -Dsonar.sources=. \
  -Dsonar.host.url=http://localhost:9002 \
  -Dsonar.login=<token>
```

---
**Generated:** 2026-01-17 22:10:02
