"""Putting extracted rules back into the policies the document stated them as.

A paragraph is one policy. It may state several rules. The extractor emits one
record per rule, which is right -- "the department head will review and approve
the leave application" is two decisions and a reviewer needs to see both. What
was missing is the container: those two records were presented as two policies,
so a document stating 193 policies read as one stating 411.

Nothing here merges, rewrites, composes or removes anything. The rules are
exactly the rules. Assembly is a grouping derived on read from provenance the
records already carry, so a wrong key is corrected by changing the key rather
than by migrating data, and extraction never has to know this exists.
"""
