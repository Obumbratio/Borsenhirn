"""Constantes de acción para el audit log (B5)."""


class AuditAction:
    # Credenciales (claves de broker)
    CRED_READ = "credentials.read"
    CRED_WRITE = "credentials.write"
    CRED_DELETE = "credentials.delete"
    CRED_ROTATE = "credentials.rotate"
    # Billing
    BILLING_UPDATED = "billing.subscription.updated"
    # Lifecycle de tenant
    TENANT_PROVISIONED = "tenant.provisioned"
    TENANT_SUSPENDED = "tenant.suspended"
    TENANT_DISABLED = "tenant.disabled"
    TENANT_REACTIVATED = "tenant.reactivated"
    # Kill-switch
    KS_HALT = "killswitch.halt"
    KS_CLEAR = "killswitch.clear"
    KS_GLOBAL_HALT = "killswitch.global_halt"
    KS_GLOBAL_CLEAR = "killswitch.global_clear"


__all__ = ["AuditAction"]
