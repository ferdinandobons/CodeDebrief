<?php

namespace Catalog;

class Catalog
{
    public function reorderQuantity(string $availability, int $onHand): int
    {
        switch ($availability) {
            case "in_stock":
                return 0;
            case "low_stock":
                return $this->restockTarget() - $onHand;
            case "out_of_stock":
                return $this->restockTarget();
            case "discontinued":
                return 0;
            default:
                return 0;
        }
    }

    private function restockTarget(): int
    {
        return 100;
    }
}
